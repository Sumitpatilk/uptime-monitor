from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import CheckResult, Incident
from app.services.check_engine import perform_http_check


def update_incident_status(
    monitor_id: UUID,
    db: Session,
):
    statement = (
        select(CheckResult.status)
        .where(CheckResult.monitor_id == monitor_id)
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
            Incident.monitor_id == monitor_id,
            Incident.state == "open",
        )
        .order_by(desc(Incident.started_at))
        .limit(1)
    )

    open_incident = db.scalars(incident_statement).first()

    if (
        len(recent_statuses) >= 3
        and all(check_status == "down" for check_status in recent_statuses)
    ):
        if not open_incident:
            db.add(
                Incident(
                    monitor_id=monitor_id,
                    state="open",
                    summary="Monitor is down after 3 consecutive failed checks.",
                )
            )

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

    update_incident_status(monitor.id, db)

    db.commit()
    db.refresh(check_result)

    return check_result
