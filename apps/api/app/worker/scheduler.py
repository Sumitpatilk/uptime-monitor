
import logging
import signal
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.entities import CheckResult, Monitor
from app.services.check_runner import run_monitor_check
from app.services.notification_service import process_due_notifications
from app.services.retention_service import cleanup_old_check_results


POLL_INTERVAL_SECONDS = 5
RETENTION_CLEANUP_INTERVAL_SECONDS = 3600

shutdown_event = threading.Event()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

logger = logging.getLogger("uptime-monitor.scheduler")


def handle_shutdown_signal(signum, frame):
    """Request graceful shutdown on SIGTERM or SIGINT."""

    if not shutdown_event.is_set():
        logger.info(
            "Shutdown signal received (%s). "
            "Finishing current scheduler cycle...",
            signal.Signals(signum).name,
        )
        shutdown_event.set()


def is_monitor_due(
    monitor: Monitor,
    db: Session,
    current_time: datetime,
) -> bool:
    last_checked_at = db.scalar(
        select(func.max(CheckResult.checked_at)).where(
            CheckResult.monitor_id == monitor.id
        )
    )

    if last_checked_at is None:
        return True

    if last_checked_at.tzinfo is None:
        last_checked_at = last_checked_at.replace(
            tzinfo=timezone.utc
        )

    elapsed_seconds = (
        current_time - last_checked_at
    ).total_seconds()

    return elapsed_seconds >= monitor.interval_seconds


def process_due_monitors(
    db: Session,
    shutdown_event=None,
):
    current_time = datetime.now(timezone.utc)

    monitor_ids = db.scalars(
        select(Monitor.id)
        .where(Monitor.enabled.is_(True))
        .order_by(Monitor.created_at)
    ).all()

    for monitor_id in monitor_ids:

        if shutdown_event is not None and shutdown_event.is_set():
            logger.info(
                "Monitor processing stopped: shutdown requested."
            )
            break

        try:
            # Atomically acquire the monitor row lock.
            monitor = db.scalar(
                select(Monitor)
                .where(
                    Monitor.id == monitor_id,
                    Monitor.enabled.is_(True),
                )
                .with_for_update(skip_locked=True)
            )

            # Another worker may already be checking this monitor.
            if monitor is None:
                db.rollback()
                continue

            if not is_monitor_due(monitor, db, current_time):
                db.rollback()
                continue

            logger.info(
                "Starting check for monitor '%s' (%s)",
                monitor.name,
                monitor.id,
            )

            result = run_monitor_check(monitor, db, monitor_locked=True)

            logger.info(
                "Check completed: monitor='%s', status='%s', "
                "status_code=%s, latency_ms=%s, error_code=%s",
                monitor.name,
                result.status,
                result.status_code,
                result.latency_ms,
                result.error_code,
            )

        except Exception:
            db.rollback()

            logger.exception(
                "Check failed for monitor '%s' (%s)",
                monitor.name,
                monitor_id,
            )


def run_scheduler():
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)

    shutdown_event.clear()
    last_retention_cleanup = 0.0

    logger.info(
        "Uptime Monitor Scheduler started. Poll interval: %s seconds",
        POLL_INTERVAL_SECONDS,
    )

    try:
        while not shutdown_event.is_set():
            db = SessionLocal()

            try:
                process_due_monitors(db, shutdown_event)

                process_due_notifications(db, shutdown_event)

                current_monotonic = time.monotonic()
                if (
                    not shutdown_event.is_set()
                    and current_monotonic - last_retention_cleanup
                    >= RETENTION_CLEANUP_INTERVAL_SECONDS
                ):
                    last_retention_cleanup = current_monotonic
                    retention_db = SessionLocal()
                    try:
                        deleted_count = cleanup_old_check_results(
                            retention_db
                        )
                        logger.info(
                            "Retention cleanup cycle completed: "
                            "deleted_count=%s",
                            deleted_count,
                        )
                    except Exception:
                        logger.exception(
                            "Retention cleanup cycle failed"
                        )
                    finally:
                        retention_db.close()

            except SQLAlchemyError:
                db.rollback()
                logger.exception("Database error in scheduler")

            except Exception:
                db.rollback()
                logger.exception("Unexpected scheduler error")

            finally:
                db.close()

            if not shutdown_event.is_set():
                shutdown_event.wait(POLL_INTERVAL_SECONDS)

    finally:
        logger.info("Uptime Monitor Scheduler stopped gracefully.")


if __name__ == "__main__":
    run_scheduler()
