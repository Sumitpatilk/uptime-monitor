from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AlertChannel,
    CheckResult,
    Incident,
    NotificationEvent,
)
from app.services.check_engine import perform_http_check


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
        existing_event = db.scalar(
            select(NotificationEvent).where(
                NotificationEvent.incident_id == incident.id,
                NotificationEvent.channel_id == channel.id,
                NotificationEvent.event_type == event_type,
            )
        )

        if existing_event:
            continue

        db.add(
            NotificationEvent(
                incident_id=incident.id,
                channel_id=channel.id,
                event_type=event_type,
                status="pending",
                attempts=0,
            )
        )


def update_incident_status(
    monitor,
    db: Session,
):
    statement = (
        select(CheckResult.status)
        .where(CheckResult.monitor_id == monitor.id)
        .order_by(
            desc(CheckResult.checked_at),
            desc(CheckResult.id),
        )
        .limit(3)
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

    # Open an incident after 3 consecutive failed checks.
    if (
        len(recent_statuses) >= 3
        and all(check_status == "down" for check_status in recent_statuses)
    ):
        if not open_incident:
            new_incident = Incident(
                monitor_id=monitor.id,
                state="open",
                summary="Monitor is down after 3 consecutive failed checks.",
            )

            db.add(new_incident)
            db.flush()

            create_notification_events(
                incident=new_incident,
                monitor=monitor,
                event_type="incident_opened",
                db=db,
            )

    # Resolve an open incident after 2 consecutive successful checks.
    if (
        len(recent_statuses) >= 2
        and all(check_status == "up" for check_status in recent_statuses[:2])
    ):
        if open_incident:
            open_incident.state = "resolved"
            open_incident.resolved_at = datetime.now(timezone.utc)
            open_incident.summary = (
                "Monitor recovered after 2 consecutive successful checks."
            )

            create_notification_events(
                incident=open_incident,
                monitor=monitor,
                event_type="incident_resolved",
                db=db,
            )


def run_monitor_check(monitor, db: Session) -> CheckResult:
    if not monitor.enabled:
        raise ValueError("This monitor is disabled.")

    check_data = perform_http_check(monitor)

    check_result = CheckResult(
        monitor_id=monitor.id,
        **check_data,
    )

    db.add(check_result)
    db.flush()

    update_incident_status(monitor, db)

    db.commit()
    db.refresh(check_result)

    return check_result
