import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.entities import (
    AlertChannel,
    Incident,
    Monitor,
    NotificationEvent,
)
from app.services.email_service import send_email


logger = logging.getLogger("uptime-monitor.notifications")

MAX_ATTEMPTS = 5

RETRY_DELAYS_SECONDS = [
    60,
    120,
    240,
    480,
]

BATCH_SIZE = 50
STALE_LOCK_SECONDS = 300


def build_notification_content(
    event: NotificationEvent,
    incident: Incident,
    monitor: Monitor,
):
    """Build notification subject and body."""

    if event.event_type == "incident_opened":
        subject = f"ALERT: {monitor.name} is DOWN"
        message = (
            f"Monitor: {monitor.name}\n"
            f"URL: {monitor.url}\n"
            f"Status: DOWN\n"
            f"Incident: {incident.id}\n"
            f"Summary: {incident.summary}\n"
        )

    elif event.event_type == "incident_resolved":
        subject = f"RECOVERED: {monitor.name} is UP"
        message = (
            f"Monitor: {monitor.name}\n"
            f"URL: {monitor.url}\n"
            f"Status: UP\n"
            f"Incident: {incident.id}\n"
            f"Summary: {incident.summary}\n"
        )

    else:
        raise ValueError(
            f"Unsupported notification event: {event.event_type}"
        )

    return subject, message


def _mark_failed(
    event: NotificationEvent,
    db: Session,
    error: str,
):
    event.status = "failed"
    event.last_error = error[:5000]
    event.next_attempt_at = None
    event.locked_at = None

    db.commit()

    logger.error(
        "Notification permanently failed: event=%s error=%s",
        event.id,
        error,
    )



def _recover_stale_notifications(db: Session):
    """Return notifications with expired processing locks to retry."""

    now = datetime.now(timezone.utc)

    stale_before = now - timedelta(
        seconds=STALE_LOCK_SECONDS
    )

    result = db.execute(
        update(NotificationEvent)
        .where(
            NotificationEvent.status == "processing",
            NotificationEvent.locked_at.is_not(None),
            NotificationEvent.locked_at <= stale_before,
        )
        .values(
            status="retry",
            locked_at=None,
            next_attempt_at=now,
            last_error=(
                "Processing lock expired. "
                "Notification returned to retry queue."
            ),
        )
        .execution_options(synchronize_session=False)
    )

    recovered_count = result.rowcount or 0

    db.commit()

    if recovered_count:
        logger.warning(
            "Recovered %s stale notification events",
            recovered_count,
        )


def _claim_next_notification(db: Session):
    """Atomically claim one due notification."""

    now = datetime.now(timezone.utc)

    statement = (
        select(NotificationEvent)
        .where(
            NotificationEvent.status.in_(["pending", "retry"]),
            (
                NotificationEvent.next_attempt_at.is_(None)
                | (NotificationEvent.next_attempt_at <= now)
            ),
        )
        .order_by(
            NotificationEvent.next_attempt_at.nullsfirst()
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    event = db.scalars(statement).first()

    if event is None:
        db.rollback()
        return None

    event_id = event.id

    event.status = "processing"
    event.locked_at = now

    db.commit()

    logger.info(
        "Notification claimed: event=%s",
        event_id,
    )

    return event_id


def process_notification_event(
    event_id,
    db: Session,
):
    """Process an already claimed notification."""

    event = db.get(NotificationEvent, event_id)

    if event is None or event.status != "processing":
        return

    if event.attempts >= MAX_ATTEMPTS:
        _mark_failed(
            event,
            db,
            "Maximum notification attempts exceeded.",
        )
        return

    try:
        channel = db.get(AlertChannel, event.channel_id)

        if channel is None or not channel.enabled:
            _mark_failed(
                event,
                db,
                "Alert channel is missing or disabled.",
            )
            return

        if channel.type != "email":
            _mark_failed(
                event,
                db,
                f"Unsupported channel type: {channel.type}",
            )
            return

        incident = db.get(Incident, event.incident_id)

        if incident is None:
            _mark_failed(
                event,
                db,
                "Related incident not found.",
            )
            return

        monitor = db.get(Monitor, incident.monitor_id)

        if monitor is None:
            _mark_failed(
                event,
                db,
                "Related monitor not found.",
            )
            return
        if channel.project_id != monitor.project_id:
            _mark_failed(
                event,
                db,
                "Alert channel and monitor belong to different projects.",
            )
            return

        subject, body = build_notification_content(
            event,
            incident,
            monitor,
        )

        send_email(
            to_email=channel.destination,
            subject=subject,
            body=body,
        )

        event.attempts += 1
        event.status = "sent"
        event.sent_at = datetime.now(timezone.utc)
        event.last_error = None
        event.next_attempt_at = None
        event.locked_at = None

        db.commit()

        logger.info(
            "Notification sent: event=%s attempts=%s",
            event_id,
            event.attempts,
        )

    except Exception as exc:
        db.rollback()

        event = db.get(NotificationEvent, event_id)

        if event is None or event.status != "processing":
            return

        event.attempts += 1
        event.last_error = str(exc)[:5000]
        event.locked_at = None

        if event.attempts >= MAX_ATTEMPTS:
            event.status = "failed"
            event.next_attempt_at = None

            logger.error(
                "Notification permanently failed: "
                "event=%s attempts=%s",
                event_id,
                event.attempts,
            )

        else:
            delay = RETRY_DELAYS_SECONDS[
                event.attempts - 1
            ]

            event.status = "retry"
            event.next_attempt_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=delay)
            )

            logger.warning(
                "Notification retry scheduled: "
                "event=%s attempt=%s delay=%s seconds error=%s",
                event_id,
                event.attempts,
                delay,
                exc,
            )

        db.commit()



def process_due_notifications(
    db: Session,
    shutdown_event=None,
):
    """Claim and process due notifications safely."""

    if shutdown_event is not None and shutdown_event.is_set():
        logger.info(
            "Notification processing skipped: shutdown requested."
        )
        return

    _recover_stale_notifications(db)

    for _ in range(BATCH_SIZE):

        # Do not claim another notification during shutdown.
        if shutdown_event is not None and shutdown_event.is_set():
            logger.info(
                "Notification processing stopped: shutdown requested."
            )
            break

        try:
            event_id = _claim_next_notification(db)

            if event_id is None:
                break

            # Complete the already-claimed notification.
            process_notification_event(event_id, db)

        except Exception:
            db.rollback()

            logger.exception(
                "Unexpected notification processing error"
            )
