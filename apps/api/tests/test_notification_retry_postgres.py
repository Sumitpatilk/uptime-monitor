import uuid
from datetime import datetime, timedelta, timezone

from app.models.entities import (
    AlertChannel,
    Incident,
    Monitor,
    NotificationEvent,
    Project,
    User,
)
from app.services.notification_service import (
    RETRY_DELAYS_SECONDS,
    process_notification_event,
)


def test_email_failure_persists_retry_schedule_in_postgres(
    test_db_session,
    monkeypatch,
):
    user = User(
        email=f"retry-postgres-{uuid.uuid4()}@example.test"
    )
    test_db_session.add(user)
    test_db_session.flush()

    project = Project(
        owner_id=user.id,
        name="Retry Integration Test",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Retry Test Monitor",
        url="https://example.test",
    )
    channel = AlertChannel(
        project_id=project.id,
        type="email",
        destination="retry@example.test",
        enabled=True,
    )
    test_db_session.add_all([monitor, channel])
    test_db_session.flush()

    incident = Incident(
        monitor_id=monitor.id,
        summary="Simulated monitor failure",
    )
    test_db_session.add(incident)
    test_db_session.flush()

    event = NotificationEvent(
        incident_id=incident.id,
        channel_id=channel.id,
        event_type="incident_opened",
        status="processing",
        attempts=0,
        locked_at=datetime.now(timezone.utc),
    )
    test_db_session.add(event)
    test_db_session.commit()

    event_id = event.id

    def fail_email(**kwargs):
        raise RuntimeError("Simulated SMTP failure")

    monkeypatch.setattr(
        "app.services.notification_service.send_email",
        fail_email,
    )

    before_processing = datetime.now(timezone.utc)

    process_notification_event(
        event_id,
        test_db_session,
    )

    after_processing = datetime.now(timezone.utc)

    test_db_session.expire_all()

    saved_event = test_db_session.get(
        NotificationEvent,
        event_id,
    )

    expected_delay = RETRY_DELAYS_SECONDS[0]

    assert saved_event.status == "retry"
    assert saved_event.attempts == 1
    assert saved_event.last_error == "Simulated SMTP failure"
    assert saved_event.locked_at is None
    assert saved_event.next_attempt_at is not None

    earliest_expected = (
        before_processing + timedelta(seconds=expected_delay)
    )
    latest_expected = (
        after_processing + timedelta(seconds=expected_delay)
    )

    assert earliest_expected <= saved_event.next_attempt_at <= latest_expected
