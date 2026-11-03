import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.models.entities import CheckResult, Monitor, Project, User
from app.services.retention_service import cleanup_old_check_results


def test_cleanup_deletes_only_expired_check_results(test_db_session, monkeypatch):
    monkeypatch.setattr(settings, "check_result_retention_days", 90)
    monkeypatch.setattr(settings, "retention_cleanup_batch_size", 1000)

    now = datetime.now(timezone.utc)

    user = User(email=f"retention-{uuid.uuid4()}@example.test")
    test_db_session.add(user)
    test_db_session.flush()

    project = Project(
        owner_id=user.id,
        name="Retention Test",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Retention Monitor",
        url="https://example.test",
        interval_seconds=60,
        enabled=True,
    )
    test_db_session.add(monitor)
    test_db_session.flush()

    expired = CheckResult(
        monitor_id=monitor.id,
        checked_at=now - timedelta(days=91),
        status="down",
    )
    recent = CheckResult(
        monitor_id=monitor.id,
        checked_at=now - timedelta(days=10),
        status="up",
    )
    test_db_session.add_all([expired, recent])
    test_db_session.flush()

    expired_id = expired.id
    recent_id = recent.id

    deleted_count = cleanup_old_check_results(
        test_db_session,
        current_time=now,
    )

    assert deleted_count == 1

    remaining_ids = set(
        test_db_session.scalars(
            select(CheckResult.id).where(
                CheckResult.monitor_id == monitor.id
            )
        ).all()
    )

    assert expired_id not in remaining_ids
    assert recent_id in remaining_ids


def test_cleanup_respects_batch_size(test_db_session, monkeypatch):
    monkeypatch.setattr(settings, "check_result_retention_days", 90)
    monkeypatch.setattr(settings, "retention_cleanup_batch_size", 1)

    now = datetime.now(timezone.utc)

    user = User(email=f"retention-batch-{uuid.uuid4()}@example.test")
    test_db_session.add(user)
    test_db_session.flush()

    project = Project(
        owner_id=user.id,
        name="Retention Batch Test",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Retention Batch Monitor",
        url="https://example.test",
        interval_seconds=60,
        enabled=True,
    )
    test_db_session.add(monitor)
    test_db_session.flush()

    test_db_session.add_all([
        CheckResult(
            monitor_id=monitor.id,
            checked_at=now - timedelta(days=100),
            status="down",
        ),
        CheckResult(
            monitor_id=monitor.id,
            checked_at=now - timedelta(days=101),
            status="down",
        ),
    ])
    test_db_session.flush()

    deleted_count = cleanup_old_check_results(
        test_db_session,
        current_time=now,
    )

    remaining_count = len(
        test_db_session.scalars(
            select(CheckResult.id).where(
                CheckResult.monitor_id == monitor.id
            )
        ).all()
    )

    assert deleted_count == 1
    assert remaining_count == 1
