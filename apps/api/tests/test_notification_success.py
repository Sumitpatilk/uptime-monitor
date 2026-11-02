from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import notification_service


def test_notification_is_marked_sent_after_successful_email(monkeypatch):
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

    assert event.status == "sent"
    assert event.attempts == 1
    assert event.sent_at is not None
    assert event.last_error is None
    assert event.next_attempt_at is None
    assert event.locked_at is None

    assert len(sent_emails) == 1
    assert sent_emails[0]["to_email"] == "sumit@example.com"

    db.commit.assert_called_once()
    db.rollback.assert_not_called()
