
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.csrf import verify_request_origin
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import CheckResult, Monitor, Project, User
from app.services.check_runner import run_monitor_check as execute_monitor_check


router = APIRouter(
    prefix="/api/projects/{project_id}/monitors",
    tags=["Checks"],
)


def get_owned_project_monitor(
    project_id: UUID,
    monitor_id: UUID,
    owner_id: UUID,
    db: Session,
) -> Monitor:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == owner_id,
        )
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    monitor = db.scalar(
        select(Monitor).where(
            Monitor.id == monitor_id,
            Monitor.project_id == project_id,
        )
    )

    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor not found.",
        )

    return monitor


@router.post(
    "/{monitor_id}/check",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def run_monitor_check(
    project_id: UUID,
    monitor_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    monitor = get_owned_project_monitor(
        project_id,
        monitor_id,
        current_user.id,
        db,
    )

    if not monitor.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This monitor is disabled.",
        )

    try:
        check_result = execute_monitor_check(monitor, db)
    except Exception:
        db.rollback()
        raise

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    monitor = get_owned_project_monitor(
        project_id,
        monitor_id,
        current_user.id,
        db,
    )

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
