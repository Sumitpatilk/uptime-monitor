
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Monitor, Project
from app.schemas.monitor import MonitorCreate, MonitorRead, MonitorUpdate


router = APIRouter(
    prefix="/api/projects/{project_id}/monitors",
    tags=["Monitors"],
)


def get_existing_project(project_id: UUID, db: Session) -> Project:
    project = db.get(Project, project_id)

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
)
def create_monitor(
    project_id: UUID,
    payload: MonitorCreate,
    db: Session = Depends(get_db),
):
    get_existing_project(project_id, db)

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
    db: Session = Depends(get_db),
):
    get_existing_project(project_id, db)

    statement = (
        select(Monitor)
        .where(Monitor.project_id == project_id)
        .order_by(Monitor.created_at.desc())
    )

    return db.scalars(statement).all()


@router.patch("/{monitor_id}", response_model=MonitorRead)
def update_monitor(
    project_id: UUID,
    monitor_id: UUID,
    payload: MonitorUpdate,
    db: Session = Depends(get_db),
):
    get_existing_project(project_id, db)

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
)
def delete_monitor(
    project_id: UUID,
    monitor_id: UUID,
    db: Session = Depends(get_db),
):
    get_existing_project(project_id, db)

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
