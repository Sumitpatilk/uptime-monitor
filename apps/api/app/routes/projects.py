from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import (
    AlertChannel,
    AuditEvent,
    Monitor,
    Project,
    StatusPage,
    User,
)
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate


router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"],
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
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: ProjectCreate,
    owner_id: UUID,
    db: Session = Depends(get_db),
):
    user = db.get(User, owner_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    project = Project(
        owner_id=owner_id,
        name=payload.name,
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(
    owner_id: UUID,
    db: Session = Depends(get_db),
):
    statement = (
        select(Project)
        .where(Project.owner_id == owner_id)
        .order_by(Project.created_at.desc())
    )

    return db.scalars(statement).all()


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: UUID,
    owner_id: UUID,
    db: Session = Depends(get_db),
):
    return get_owned_project(project_id, owner_id, db)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    owner_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_owned_project(project_id, owner_id, db)

    update_data = payload.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields provided.",
        )

    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    owner_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_owned_project(project_id, owner_id, db)

    dependent_models = (
        Monitor,
        AlertChannel,
        StatusPage,
        AuditEvent,
    )

    for model in dependent_models:
        dependent_record = db.scalar(
            select(model.id)
            .where(model.project_id == project_id)
            .limit(1)
        )

        if dependent_record is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cannot delete this project while it has monitors, "
                    "alert channels, status pages, or audit events."
                ),
            )

    db.delete(project)
    db.commit()

    return None
