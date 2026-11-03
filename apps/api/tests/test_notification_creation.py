from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.services.check_runner import create_notification_events


def make_notification_context():
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

    return incident, monitor, db


def test_notification_insert_uses_on_conflict_do_nothing():
    incident, monitor, db = make_notification_context()

    create_notification_events(
        incident, monitor, "incident_opened", db
    )

    db.execute.assert_called_once()

    statement = db.execute.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "INSERT INTO notification_events" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_notification_incident_channel_event DO NOTHING" in sql

    assert compiled.params["incident_id"] == incident.id
    assert compiled.params["channel_id"] == "channel-1"
    assert compiled.params["event_type"] == "incident_opened"
    assert compiled.params["status"] == "pending"
    assert compiled.params["attempts"] == 0


def test_no_notification_insert_when_no_enabled_channels():
    incident = SimpleNamespace(id="incident-1")
    monitor = SimpleNamespace(project_id="project-1")

    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    create_notification_events(
        incident, monitor, "incident_opened", db
    )

    db.execute.assert_not_called()
