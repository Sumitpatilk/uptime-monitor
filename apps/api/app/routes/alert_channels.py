
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.csrf import verify_request_origin
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import AlertChannel, Project, User
from app.schemas.alert_channel import (
    AlertChannelCreate,
    AlertChannelRead,
    AlertChannelUpdate,
)


router = APIRouter(
    prefix="/api/projects/{project_id}/alert-channels",
    tags=["Alert Channels"],
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
    response_model=AlertChannelRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def create_alert_channel(
    project_id: UUID,
    payload: AlertChannelCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    existing_channel = db.scalar(
        select(AlertChannel).where(
            AlertChannel.project_id == project_id,
            AlertChannel.type == payload.type,
            AlertChannel.destination == payload.destination,
        )
    )

    if existing_channel:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email alert channel already exists.",
        )

    alert_channel = AlertChannel(
        project_id=project_id,
        type=payload.type,
        destination=payload.destination,
        enabled=True,
    )

    db.add(alert_channel)
    db.commit()
    db.refresh(alert_channel)

    return alert_channel


@router.get(
    "",
    response_model=list[AlertChannelRead],
)
def list_alert_channels(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    statement = (
        select(AlertChannel)
        .where(AlertChannel.project_id == project_id)
        .order_by(AlertChannel.id)
    )

    return db.scalars(statement).all()


@router.patch(
    "/{channel_id}",
    response_model=AlertChannelRead,
    dependencies=[Depends(verify_request_origin)],
)
def update_alert_channel(
    project_id: UUID,
    channel_id: UUID,
    payload: AlertChannelUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    alert_channel = db.scalar(
        select(AlertChannel).where(
            AlertChannel.id == channel_id,
            AlertChannel.project_id == project_id,
        )
    )

    if not alert_channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert channel not found.",
        )

    alert_channel.enabled = payload.enabled

    db.commit()
    db.refresh(alert_channel)

    return alert_channel


@router.delete(
    "/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_request_origin)],
)
def delete_alert_channel(
    project_id: UUID,
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_project(project_id, current_user.id, db)

    alert_channel = db.scalar(
        select(AlertChannel).where(
            AlertChannel.id == channel_id,
            AlertChannel.project_id == project_id,
        )
    )

    if not alert_channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert channel not found.",
        )

    db.delete(alert_channel)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
