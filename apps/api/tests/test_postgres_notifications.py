import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.entities import (
    AlertChannel,
    Incident,
    Monitor,
    NotificationEvent,
    Project,
    User,
)


def test_notification_event_foreign_keys_and_unique_constraint(test_db_session):
    user = User(email=f"notification-{uuid.uuid4()}@example.test")
    test_db_session.add(user)
    test_db_session.flush()

    project = Project(
        owner_id=user.id,
        name="Notification Integration Project",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Notification Test Monitor",
        url="https://example.test",
    )
    channel = AlertChannel(
        project_id=project.id,
        type="email",
        destination="alerts@example.test",
        enabled=True,
    )
    test_db_session.add_all([monitor, channel])
    test_db_session.flush()

    incident = Incident(monitor_id=monitor.id)
    test_db_session.add(incident)
    test_db_session.flush()

    event = NotificationEvent(
        incident_id=incident.id,
        channel_id=channel.id,
        event_type="incident_opened",
        status="pending",
        attempts=0,
    )
    test_db_session.add(event)
    test_db_session.commit()

    saved_event = test_db_session.scalar(
        select(NotificationEvent).where(
            NotificationEvent.id == event.id
        )
    )

    assert saved_event is not None
    assert saved_event.incident_id == incident.id
    assert saved_event.channel_id == channel.id
    assert saved_event.status == "pending"

    duplicate = NotificationEvent(
        incident_id=incident.id,
        channel_id=channel.id,
        event_type="incident_opened",
        status="pending",
        attempts=0,
    )

    with pytest.raises(IntegrityError):
        with test_db_session.begin_nested():
            test_db_session.add(duplicate)
            test_db_session.flush()

    event_count = test_db_session.scalar(
        select(func.count()).select_from(NotificationEvent).where(
            NotificationEvent.incident_id == incident.id,
            NotificationEvent.channel_id == channel.id,
            NotificationEvent.event_type == "incident_opened",
        )
    )

    assert event_count == 1
