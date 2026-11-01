from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import CheckResult, Incident, Monitor, Project
from app.services.check_engine import perform_http_check


router = APIRouter(
    prefix="/api/projects/{project_id}/monitors",
    tags=["Checks"],
)


def get_project_monitor(
    project_id: UUID,
    monitor_id: UUID,
    db: Session,
):
    project = db.get(Project, project_id)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    monitor = db.get(Monitor, monitor_id)

    if not monitor or monitor.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor not found.",
        )

    return monitor


def update_incident_status(
    monitor_id: UUID,
    db: Session,
):
    # Fetch the latest three check results.
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

    # Find an existing open incident.
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

    # Three consecutive failures: open an incident.
    if (
        len(recent_statuses) >= 3
        and all(check_status == "down" for check_status in recent_statuses)
    ):
        if not open_incident:
            incident = Incident(
                monitor_id=monitor_id,
                state="open",
                summary="Monitor is down after 3 consecutive failed checks.",
            )

            db.add(incident)

    # Two consecutive successful checks: resolve an incident.
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


@router.post(
    "/{monitor_id}/check",
    status_code=status.HTTP_201_CREATED,
)
def run_monitor_check(
    project_id: UUID,
    monitor_id: UUID,
    db: Session = Depends(get_db),
):
    monitor = get_project_monitor(project_id, monitor_id, db)

    if not monitor.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This monitor is disabled.",
        )

    # Execute HTTP check.
    check_data = perform_http_check(monitor)

    # Save check result.
    check_result = CheckResult(
        monitor_id=monitor.id,
        **check_data,
    )

    db.add(check_result)
    db.flush()

    # Evaluate incident conditions using saved check history.
    update_incident_status(monitor.id, db)

    # Save check and incident changes.
    db.commit()
    db.refresh(check_result)

    return {
        "id": str(check_result.id),
        "monitor_id": str(check_result.monitor_id),
        "checked_at": check_result.checked_at,
        "status": check_result.status,
        "status_code": check_result.status_code,
        "latency_ms": check_result.latency_ms,
        "error_code": check_result.error_code,
    }


@router.get("/{monitor_id}/checks")
def get_monitor_check_history(
    project_id: UUID,
    monitor_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    monitor = get_project_monitor(project_id, monitor_id, db)

    statement = (
        select(CheckResult)
        .where(CheckResult.monitor_id == monitor.id)
        .order_by(
            desc(CheckResult.checked_at),
            desc(CheckResult.id),
        )
        .limit(limit)
        .offset(offset)
    )

    results = db.scalars(statement).all()

    return {
        "monitor_id": str(monitor.id),
        "count": len(results),
        "limit": limit,
        "offset": offset,
        "checks": [
            {
                "id": str(check.id),
                "checked_at": check.checked_at,
                "status": check.status,
                "status_code": check.status_code,
                "latency_ms": check.latency_ms,
                "error_code": check.error_code,
            }
            for check in results
        ],
    }
