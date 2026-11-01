import logging
import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.entities import CheckResult, Monitor
from app.services.check_runner import run_monitor_check


POLL_INTERVAL_SECONDS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

logger = logging.getLogger("uptime-monitor.scheduler")


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

    # A monitor without previous checks should run immediately.
    if last_checked_at is None:
        return True

    if last_checked_at.tzinfo is None:
        last_checked_at = last_checked_at.replace(tzinfo=timezone.utc)

    elapsed_seconds = (
        current_time - last_checked_at
    ).total_seconds()

    return elapsed_seconds >= monitor.interval_seconds


def process_due_monitors(db: Session):
    current_time = datetime.now(timezone.utc)

    monitors = db.scalars(
        select(Monitor)
        .where(Monitor.enabled.is_(True))
        .order_by(Monitor.created_at)
    ).all()

    for monitor in monitors:
        monitor_id = monitor.id
        monitor_name = monitor.name

        try:
            if not is_monitor_due(monitor, db, current_time):
                continue

            logger.info(
                "Starting check for monitor '%s' (%s)",
                monitor_name,
                monitor_id,
            )

            result = run_monitor_check(monitor, db)

            logger.info(
                "Check completed: monitor='%s', status='%s', "
                "status_code=%s, latency_ms=%s, error_code=%s",
                monitor_name,
                result.status,
                result.status_code,
                result.latency_ms,
                result.error_code,
            )

        except Exception:
            db.rollback()

            logger.exception(
                "Check failed for monitor '%s' (%s)",
                monitor_name,
                monitor_id,
            )


def run_scheduler():
    logger.info(
        "Uptime Monitor Scheduler started. Poll interval: %s seconds",
        POLL_INTERVAL_SECONDS,
    )

    while True:
        db = SessionLocal()

        try:
            process_due_monitors(db)

        except SQLAlchemyError:
            db.rollback()
            logger.exception("Database error in scheduler")

        except Exception:
            db.rollback()
            logger.exception("Unexpected scheduler error")

        finally:
            db.close()

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_scheduler()
