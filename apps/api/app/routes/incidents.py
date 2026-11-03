from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import Incident, Monitor, Project, User
from app.schemas.incident import IncidentRead


router = APIRouter(
    prefix="/api/projects/{project_id}/incidents",
    tags=["Incidents"],
)


def get_owned_incident(
    project_id: UUID,
    incident_id: UUID,
    owner_id: UUID,
    db: Session,
) -> Incident:
    statement = (
        select(Incident)
        .join(Monitor, Incident.monitor_id == Monitor.id)
        .join(Project, Monitor.project_id == Project.id)
        .where(
            Project.id == project_id,
            Project.owner_id == owner_id,
            Incident.id == incident_id,
        )
    )

    incident = db.scalar(statement)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found.",
        )

    return incident


@router.get("", response_model=list[IncidentRead])
def list_incidents(
    project_id: UUID,
    state: str | None = Query(default=None, pattern="^(open|resolved)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id,
        )
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    statement = (
        select(Incident)
        .join(Monitor, Incident.monitor_id == Monitor.id)
        .where(Monitor.project_id == project_id)
    )

    if state is not None:
        statement = statement.where(Incident.state == state)

    statement = (
        statement
        .order_by(desc(Incident.started_at), desc(Incident.id))
        .limit(limit)
        .offset(offset)
    )

    return db.scalars(statement).all()


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(
    project_id: UUID,
    incident_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_owned_incident(
        project_id,
        incident_id,
        current_user.id,
        db,
    )
