
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import notification_service


def test_notification_is_rejected_when_channel_and_monitor_projects_differ(
    monkeypatch,
):
    event = SimpleNamespace(
        id="event-1",
        status="processing",
        attempts=0,
        channel_id="channel-1",
        incident_id="incident-1",
        event_type="incident_opened",
        locked_at=datetime.now(timezone.utc),
        next_attempt_at=None,
        last_error=None,
        sent_at=None,
    )

    channel = SimpleNamespace(
        id="channel-1",
        project_id="project-1",
        type="email",
        destination="sumit@example.com",
        enabled=True,
    )

    incident = SimpleNamespace(
        id="incident-1",
        monitor_id="monitor-1",
        summary="Monitor is down",
    )

    monitor = SimpleNamespace(
        id="monitor-1",
        project_id="project-2",
        name="Example Website",
        url="https://example.com",
    )

    db = MagicMock()
    db.get.side_effect = [
        event,
        channel,
        incident,
        monitor,
    ]

    sent_emails = []

    def mock_send_email(**kwargs):
        sent_emails.append(kwargs)

    monkeypatch.setattr(
        notification_service,
        "send_email",
        mock_send_email,
    )

    notification_service.process_notification_event(
        "event-1",
        db,
    )

    assert event.status == "failed"
    assert event.last_error == (
        "Alert channel and monitor belong to different projects."
    )
    assert event.attempts == 0
    assert event.locked_at is None
    assert event.next_attempt_at is None

    assert sent_emails == []

    db.commit.assert_called_once()
    db.rollback.assert_not_called()
