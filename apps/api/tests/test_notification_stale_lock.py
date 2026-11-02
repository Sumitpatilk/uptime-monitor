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
    STALE_LOCK_SECONDS,
    _recover_stale_notifications,
)


def test_stale_processing_notification_returns_to_retry_queue(
    test_db_session,
):
    user = User(
        email=f"stale-lock-{uuid.uuid4()}@example.test"
    )
    test_db_session.add(user)
    test_db_session.flush()

    project = Project(
        owner_id=user.id,
        name="Stale Lock Recovery Test",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Stale Lock Test Monitor",
        url="https://example.test",
    )
    channel = AlertChannel(
        project_id=project.id,
        type="email",
        destination="stale-lock@example.test",
        enabled=True,
    )
    test_db_session.add_all([monitor, channel])
    test_db_session.flush()

    incident = Incident(monitor_id=monitor.id)
    test_db_session.add(incident)
    test_db_session.flush()

    now = datetime.now(timezone.utc)

    stale_event = NotificationEvent(
        incident_id=incident.id,
        channel_id=channel.id,
        event_type="incident_opened",
        status="processing",
        attempts=1,
        locked_at=now - timedelta(
            seconds=STALE_LOCK_SECONDS + 60
        ),
    )

    fresh_event = NotificationEvent(
        incident_id=incident.id,
        channel_id=channel.id,
        event_type="incident_resolved",
        status="processing",
        attempts=1,
        locked_at=now - timedelta(seconds=60),
    )

    test_db_session.add_all([stale_event, fresh_event])
    test_db_session.commit()

    stale_event_id = stale_event.id
    fresh_event_id = fresh_event.id

    # Recover only notifications whose locks have expired.
    _recover_stale_notifications(test_db_session)

    test_db_session.expire_all()

    recovered_event = test_db_session.get(
        NotificationEvent,
        stale_event_id,
    )
    untouched_event = test_db_session.get(
        NotificationEvent,
        fresh_event_id,
    )

    assert recovered_event.status == "retry"
    assert recovered_event.locked_at is None
    assert recovered_event.next_attempt_at is not None
    assert recovered_event.last_error is not None
    assert "lock expired" in recovered_event.last_error.lower()

    assert untouched_event.status == "processing"
    assert untouched_event.locked_at is not None
    assert untouched_event.next_attempt_at is None
