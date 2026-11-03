import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings

from app.models.entities import (
    AlertChannel,
    CheckResult,
    Incident,
    NotificationEvent,
    Monitor,
    Project,
    User,
)
from app.services.check_runner import update_incident_status


def create_monitor(db):
    user = User(
        email=f"incident-test-{uuid.uuid4()}@example.test",
        password_hash="test-password-hash",
    )
    db.add(user)
    db.flush()

    project = Project(
        owner_id=user.id,
        name="Incident Test Project",
        plan="free",
    )
    db.add(project)
    db.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Incident Test Monitor",
        url="https://example.com",
        interval_seconds=60,
        timeout_seconds=10,
        expected_status=200,
        enabled=True,
    )
    db.add(monitor)
    db.flush()

    return project, monitor


def add_check(db, monitor, status, checked_at):
    db.add(
        CheckResult(
            monitor_id=monitor.id,
            status=status,
            status_code=200 if status == "up" else 500,
            latency_ms=100,
            error_code=None if status == "up" else "unexpected_status",
            checked_at=checked_at,
        )
    )
    db.flush()


def test_incident_opens_after_three_consecutive_failures(test_db_session):
    db = test_db_session
    project, monitor = create_monitor(db)

    channel = AlertChannel(
        project_id=project.id,
        type="email",
        destination="alerts@example.test",
        enabled=True,
    )
    db.add(channel)
    db.flush()

    base_time = datetime.now(timezone.utc)

    add_check(db, monitor, "down", base_time)
    add_check(db, monitor, "down", base_time + timedelta(seconds=60))

    update_incident_status(monitor, db)

    incidents = db.scalars(
        select(Incident).where(Incident.monitor_id == monitor.id)
    ).all()

    assert len(incidents) == 0

    add_check(db, monitor, "down", base_time + timedelta(seconds=120))

    update_incident_status(monitor, db)

    incidents = db.scalars(
        select(Incident).where(Incident.monitor_id == monitor.id)
    ).all()

    assert len(incidents) == 1
    assert incidents[0].state == "open"

    events = db.scalars(
        select(NotificationEvent).where(
            NotificationEvent.incident_id == incidents[0].id
        )
    ).all()

    assert len(events) == 1
    assert events[0].event_type == "incident_opened"
    assert events[0].status == "pending"


def test_incident_resolves_after_two_consecutive_successes(test_db_session):
    db = test_db_session
    project, monitor = create_monitor(db)

    incident = Incident(
        monitor_id=monitor.id,
        state="open",
        summary="Monitor is down.",
    )
    db.add(incident)

    channel = AlertChannel(
        project_id=project.id,
        type="email",
        destination="alerts@example.test",
        enabled=True,
    )
    db.add(channel)
    db.flush()

    base_time = datetime.now(timezone.utc)

    add_check(db, monitor, "down", base_time)
    add_check(db, monitor, "up", base_time + timedelta(seconds=60))

    update_incident_status(monitor, db)

    assert incident.state == "open"
    assert incident.resolved_at is None

    add_check(db, monitor, "up", base_time + timedelta(seconds=120))

    update_incident_status(monitor, db)

    assert incident.state == "resolved"
    assert incident.resolved_at is not None
    assert "recovered" in incident.summary.lower()

    events = db.scalars(
        select(NotificationEvent).where(
            NotificationEvent.incident_id == incident.id
        )
    ).all()

    assert len(events) == 1
    assert events[0].event_type == "incident_resolved"
    assert events[0].status == "pending"


def test_consecutive_failures_do_not_create_duplicate_open_incidents(
    test_db_session,
):
    db = test_db_session
    _, monitor = create_monitor(db)

    base_time = datetime.now(timezone.utc)

    for index in range(5):
        add_check(
            db,
            monitor,
            "down",
            base_time + timedelta(seconds=index * 60),
        )
        update_incident_status(monitor, db)

    incidents = db.scalars(
        select(Incident).where(Incident.monitor_id == monitor.id)
    ).all()

    assert len(incidents) == 1
    assert incidents[0].state == "open"

def test_incident_uses_configured_custom_thresholds(
    test_db_session,
    monkeypatch,
):
    db = test_db_session
    _, monitor = create_monitor(db)

    monkeypatch.setattr(settings, "incident_failure_threshold", 2)
    monkeypatch.setattr(settings, "incident_recovery_threshold", 3)

    base_time = datetime.now(timezone.utc)

    # First failure should not open an incident.
    add_check(db, monitor, "down", base_time)
    update_incident_status(monitor, db)

    incidents = db.scalars(
        select(Incident).where(Incident.monitor_id == monitor.id)
    ).all()

    assert len(incidents) == 0

    # Second consecutive failure should open an incident.
    add_check(db, monitor, "down", base_time + timedelta(seconds=60))
    update_incident_status(monitor, db)

    incidents = db.scalars(
        select(Incident).where(Incident.monitor_id == monitor.id)
    ).all()

    assert len(incidents) == 1
    assert incidents[0].state == "open"

    # Two successes should not resolve the incident.
    add_check(db, monitor, "up", base_time + timedelta(seconds=120))
    update_incident_status(monitor, db)

    add_check(db, monitor, "up", base_time + timedelta(seconds=180))
    update_incident_status(monitor, db)

    assert incidents[0].state == "open"

    # Third consecutive success should resolve the incident.
    add_check(db, monitor, "up", base_time + timedelta(seconds=240))
    update_incident_status(monitor, db)

    assert incidents[0].state == "resolved"
    assert incidents[0].resolved_at is not None
