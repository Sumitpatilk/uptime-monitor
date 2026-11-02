
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.csrf import verify_request_origin
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import Monitor, Project, User
from app.schemas.monitor import MonitorCreate, MonitorRead, MonitorUpdate


router = APIRouter(
    prefix="/api/projects/{project_id}/monitors",
    tags=["Monitors"],
)


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


@router.post(
    "",
    response_model=MonitorRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def create_monitor(
    project_id: UUID,
    payload: MonitorCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    monitor = Monitor(
        project_id=project_id,
        **payload.model_dump(),
    )

    db.add(monitor)
    db.commit()
    db.refresh(monitor)

    return monitor


@router.get("", response_model=list[MonitorRead])
def list_monitors(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    statement = (
        select(Monitor)
        .where(Monitor.project_id == project_id)
        .order_by(Monitor.created_at.desc())
    )

    return db.scalars(statement).all()


@router.patch(
    "/{monitor_id}",
    response_model=MonitorRead,
    dependencies=[Depends(verify_request_origin)],
)
def update_monitor(
    project_id: UUID,
    monitor_id: UUID,
    payload: MonitorUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

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

    update_data = payload.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields provided.",
        )

    for field, value in update_data.items():
        setattr(monitor, field, value)

    db.commit()
    db.refresh(monitor)

    return monitor


@router.delete(
    "/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_request_origin)],
)
def delete_monitor(
    project_id: UUID,
    monitor_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

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

    db.delete(monitor)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
