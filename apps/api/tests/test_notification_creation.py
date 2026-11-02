from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.entities import NotificationEvent
from app.services.check_runner import create_notification_events


def test_existing_notification_event_is_not_created_again():
    incident = SimpleNamespace(id="incident-1")
    monitor = SimpleNamespace(project_id="project-1")

    channel = SimpleNamespace(
        id="channel-1",
        project_id="project-1",
        type="email",
        enabled=True,
    )

    existing_event = SimpleNamespace(
        id="event-1",
        incident_id="incident-1",
        channel_id="channel-1",
        event_type="incident_opened",
    )

    db = MagicMock()
    db.scalars.return_value.all.return_value = [channel]
    db.scalar.return_value = existing_event

    create_notification_events(
        incident, monitor, "incident_opened", db
    )

    db.add.assert_not_called()


def test_new_notification_event_is_created():
    incident = SimpleNamespace(id="incident-1")
    monitor = SimpleNamespace(project_id="project-1")

    channel = SimpleNamespace(
        id="channel-1",
        project_id="project-1",
        type="email",
        enabled=True,
    )

    db = MagicMock()
    db.scalars.return_value.all.return_value = [channel]
    db.scalar.return_value = None

    create_notification_events(
        incident, monitor, "incident_opened", db
    )

    db.add.assert_called_once()

    created_event = db.add.call_args.args[0]

    assert isinstance(created_event, NotificationEvent)
    assert created_event.incident_id == incident.id
    assert created_event.channel_id == channel.id
    assert created_event.event_type == "incident_opened"
    assert created_event.status == "pending"
    assert created_event.attempts == 0
