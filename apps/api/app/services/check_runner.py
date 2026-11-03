from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    AlertChannel,
    CheckResult,
    Incident,
    NotificationEvent,
)
from app.services.check_engine import perform_http_check


class MonitorNotFoundError(LookupError):
    """Raised when a monitor disappears before its check starts."""


class MonitorDisabledError(ValueError):
    """Raised when a monitor is disabled before its check starts."""


def create_notification_events(
    incident: Incident,
    monitor,
    event_type: str,
    db: Session,
):
    """
    Create pending notification events for all enabled email channels
    belonging to the monitor's project.
    """

    channels = db.scalars(
        select(AlertChannel).where(
            AlertChannel.project_id == monitor.project_id,
            AlertChannel.type == "email",
            AlertChannel.enabled.is_(True),
        )
    ).all()

    for channel in channels:
        statement = (
            pg_insert(NotificationEvent)
            .values(
                incident_id=incident.id,
                channel_id=channel.id,
                event_type=event_type,
                status="pending",
                attempts=0,
            )
            .on_conflict_do_nothing(
                constraint="uq_notification_incident_channel_event"
            )
        )

        db.execute(statement)


def update_incident_status(
    monitor,
    db: Session,
):
    failure_threshold = settings.incident_failure_threshold
    recovery_threshold = settings.incident_recovery_threshold

    required_history = max(
        failure_threshold,
        recovery_threshold,
    )

    statement = (
        select(CheckResult.status)
        .where(CheckResult.monitor_id == monitor.id)
        .order_by(
            desc(CheckResult.checked_at),
            desc(CheckResult.id),
        )
        .limit(required_history)
    )

    recent_statuses = db.scalars(statement).all()

    incident_statement = (
        select(Incident)
        .where(
            Incident.monitor_id == monitor.id,
            Incident.state == "open",
        )
        .order_by(desc(Incident.started_at))
        .limit(1)
    )

    open_incident = db.scalars(incident_statement).first()

    # Open an incident after the configured consecutive failures.
    if (
        len(recent_statuses) >= failure_threshold
        and all(
            status == "down"
            for status in recent_statuses[:failure_threshold]
        )
    ):
        if not open_incident:
            new_incident = Incident(
                monitor_id=monitor.id,
                state="open",
                summary=(
                    "Monitor is down after "
                    f"{failure_threshold} consecutive failed checks."
                ),
            )

            db.add(new_incident)
            db.flush()

            create_notification_events(
                incident=new_incident,
                monitor=monitor,
                event_type="incident_opened",
                db=db,
            )

    # Resolve an open incident after configured consecutive successes.
    if (
        len(recent_statuses) >= recovery_threshold
        and all(
            status == "up"
            for status in recent_statuses[:recovery_threshold]
        )
    ):
        if open_incident:
            open_incident.state = "resolved"
            open_incident.resolved_at = datetime.now(timezone.utc)
            open_incident.summary = (
                "Monitor recovered after "
                f"{recovery_threshold} consecutive successful checks."
            )

            create_notification_events(
                incident=open_incident,
                monitor=monitor,
                event_type="incident_resolved",
                db=db,
            )


def run_monitor_check(
    monitor,
    db: Session,
    *,
    monitor_locked: bool = False,
) -> CheckResult:
    """
    Execute a monitor check while holding its database row lock.

    Manual API checks acquire the lock here.
    The scheduler may pass monitor_locked=True after acquiring
    the row with SELECT FOR UPDATE SKIP LOCKED.
    """

    from app.models.entities import Monitor

    if monitor_locked:
        locked_monitor = monitor
    else:
        locked_monitor = db.scalar(
            select(Monitor)
            .where(Monitor.id == monitor.id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )

    if locked_monitor is None:
        raise MonitorNotFoundError("Monitor no longer exists.")

    if not locked_monitor.enabled:
        raise MonitorDisabledError("This monitor is disabled.")

    check_data = perform_http_check(locked_monitor)

    check_result = CheckResult(
        monitor_id=locked_monitor.id,
        **check_data,
    )

    db.add(check_result)
    db.flush()

    update_incident_status(locked_monitor, db)

    db.commit()
    db.refresh(check_result)

    return check_result
