
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.core.csrf import verify_request_origin
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import CheckResult, Monitor, Project, User
from app.services.check_runner import (
    MonitorDisabledError,
    MonitorNotFoundError,
    run_monitor_check as execute_monitor_check,
)


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

    except MonitorNotFoundError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except MonitorDisabledError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

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

@router.get("/{monitor_id}/analytics")
def get_monitor_analytics(
    project_id: UUID,
    monitor_id: UUID,
    hours: int = Query(default=24, ge=1, le=720),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    monitor = get_owned_project_monitor(
        project_id,
        monitor_id,
        current_user.id,
        db,
    )

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    filters = (
        CheckResult.monitor_id == monitor.id,
        CheckResult.checked_at >= since,
    )

    totals = db.execute(
        select(
            func.count(CheckResult.id),
            func.coalesce(
                func.sum(case((CheckResult.status == "up", 1), else_=0)),
                0,
            ),
            func.avg(CheckResult.latency_ms),
            func.min(CheckResult.latency_ms),
            func.max(CheckResult.latency_ms),
        ).where(*filters)
    ).one()

    total_checks = int(totals[0] or 0)
    up_checks = int(totals[1] or 0)
    down_checks = total_checks - up_checks

    uptime_percentage = (
        round((up_checks / total_checks) * 100, 2)
        if total_checks
        else None
    )

    recent_checks = db.scalars(
        select(CheckResult)
        .where(*filters)
        .order_by(
            desc(CheckResult.checked_at),
            desc(CheckResult.id),
        )
        .limit(100)
    ).all()

    return {
        "monitor_id": str(monitor.id),
        "window_hours": hours,
        "since": since,
        "total_checks": total_checks,
        "up_checks": up_checks,
        "down_checks": down_checks,
        "uptime_percentage": uptime_percentage,
        "average_latency_ms": (
            round(float(totals[2]), 2) if totals[2] is not None else None
        ),
        "min_latency_ms": totals[3],
        "max_latency_ms": totals[4],
        "checks": [
            {
                "id": str(check.id),
                "checked_at": check.checked_at,
                "status": check.status,
                "latency_ms": check.latency_ms,
            }
            for check in reversed(recent_checks)
        ],
    }
