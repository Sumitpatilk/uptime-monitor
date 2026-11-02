from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import notification_service


@pytest.mark.parametrize(
    ("initial_attempts", "expected_status", "expected_delay"),
    [
        (0, "retry", 60),
        (1, "retry", 120),
        (2, "retry", 240),
        (3, "retry", 480),
        (4, "failed", None),
    ],
)
def test_notification_retry_backoff(
    monkeypatch,
    initial_attempts,
    expected_status,
    expected_delay,
):
    event = SimpleNamespace(
        id="event-1",
        status="processing",
        attempts=initial_attempts,
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
        event,
    ]

    def fail_email(**kwargs):
        raise RuntimeError("Simulated SMTP failure")

    monkeypatch.setattr(
        notification_service,
        "send_email",
        fail_email,
    )

    notification_service.process_notification_event(
        "event-1",
        db,
    )

    assert event.attempts == initial_attempts + 1
    assert event.status == expected_status
    assert event.locked_at is None
    assert "Simulated SMTP failure" in event.last_error

    if expected_delay is None:
        assert event.next_attempt_at is None
    else:
        now = datetime.now(timezone.utc)
        remaining = (
            event.next_attempt_at - now
        ).total_seconds()

        assert 0 < remaining <= expected_delay

    db.commit.assert_called_once()
    db.rollback.assert_called_once()
