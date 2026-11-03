from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_audit_event
from app.core.csrf import verify_request_origin
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import (
    CheckResult,
    Incident,
    Monitor,
    Project,
    StatusPage,
    User,
)
from app.schemas.status_page import (
    PublicIncidentStatus,
    PublicMonitorStatus,
    PublicStatusPageRead,
    StatusPageCreate,
    StatusPageRead,
    StatusPageUpdate,
)


router = APIRouter(tags=["Status Pages"])


def get_owned_project(
    project_id: UUID,
    owner_id: UUID,
    db: Session,
) -> Project:
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

    return project


def get_project_status_page(
    project_id: UUID,
    status_page_id: UUID,
    db: Session,
) -> StatusPage:
    page = db.scalar(
        select(StatusPage).where(
            StatusPage.id == status_page_id,
            StatusPage.project_id == project_id,
        )
    )

    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status page not found.",
        )

    return page


@router.post(
    "/api/projects/{project_id}/status-pages",
    response_model=StatusPageRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def create_status_page(
    project_id: UUID,
    payload: StatusPageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    page = StatusPage(
        project_id=project_id,
        **payload.model_dump(),
    )

    db.add(page)

    try:
        db.flush()
        log_audit_event(db, project_id, current_user.id, "status_page.created")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This status page slug is already in use.",
        )

    db.refresh(page)
    return page


@router.get(
    "/api/projects/{project_id}/status-pages",
    response_model=list[StatusPageRead],
)
def list_status_pages(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    return db.scalars(
        select(StatusPage)
        .where(StatusPage.project_id == project_id)
        .order_by(StatusPage.slug.asc())
    ).all()


@router.patch(
    "/api/projects/{project_id}/status-pages/{status_page_id}",
    response_model=StatusPageRead,
    dependencies=[Depends(verify_request_origin)],
)
def update_status_page(
    project_id: UUID,
    status_page_id: UUID,
    payload: StatusPageUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    page = get_project_status_page(project_id, status_page_id, db)
    update_data = payload.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields provided.",
        )

    if any(value is None for value in update_data.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Status page fields cannot be null.",
        )

    for field, value in update_data.items():
        setattr(page, field, value)

    try:
        log_audit_event(db, project_id, current_user.id, "status_page.updated")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This status page slug is already in use.",
        )

    db.refresh(page)
    return page


@router.delete(
    "/api/projects/{project_id}/status-pages/{status_page_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_request_origin)],
)
def delete_status_page(
    project_id: UUID,
    status_page_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    page = get_project_status_page(project_id, status_page_id, db)
    log_audit_event(db, project_id, current_user.id, "status_page.deleted")
    db.delete(page)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/status/{slug}",
    response_model=PublicStatusPageRead,
)
def get_public_status_page(
    slug: str,
    db: Session = Depends(get_db),
):
    page = db.scalar(
        select(StatusPage).where(
            StatusPage.slug == slug.lower(),
            StatusPage.enabled.is_(True),
            StatusPage.visibility == "public",
        )
    )

    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status page not found.",
        )

    monitors = db.scalars(
        select(Monitor)
        .where(
            Monitor.project_id == page.project_id,
            Monitor.enabled.is_(True),
        )
        .order_by(Monitor.name.asc())
    ).all()

    public_monitors = []
    has_down_monitor = False
    has_missing_check = False

    for monitor in monitors:
        latest_check = db.scalar(
            select(CheckResult)
            .where(CheckResult.monitor_id == monitor.id)
            .order_by(
                CheckResult.checked_at.desc(),
                CheckResult.id.desc(),
            )
            .limit(1)
        )

        if latest_check is None:
            has_missing_check = True
            monitor_status = "unknown"
            checked_at = None
            latency_ms = None
        else:
            monitor_status = latest_check.status
            checked_at = latest_check.checked_at
            latency_ms = latest_check.latency_ms

            if monitor_status != "up":
                has_down_monitor = True

        public_monitors.append(
            PublicMonitorStatus(
                name=monitor.name,
                status=monitor_status,
                last_checked_at=checked_at,
                latency_ms=latency_ms,
            )
        )

    open_incidents = db.scalars(
        select(Incident)
        .join(Monitor, Incident.monitor_id == Monitor.id)
        .where(
            Monitor.project_id == page.project_id,
            Incident.state == "open",
        )
        .order_by(Incident.started_at.desc())
    ).all()

    public_incidents = [
        PublicIncidentStatus(
            started_at=incident.started_at,
            resolved_at=incident.resolved_at,
            state=incident.state,
        )
        for incident in open_incidents
    ]

    if has_down_monitor or open_incidents:
        overall_status = "major_outage"
    elif has_missing_check or not monitors:
        overall_status = "unknown"
    else:
        overall_status = "operational"

    return PublicStatusPageRead(
        slug=page.slug,
        overall_status=overall_status,
        monitors=public_monitors,
        incidents=public_incidents,
    )
