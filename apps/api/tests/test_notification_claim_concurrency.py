import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.entities import (
    AlertChannel,
    Incident,
    Monitor,
    NotificationEvent,
    Project,
    User,
)
from app.services.notification_service import _claim_next_notification


def test_skip_locked_allows_second_worker_to_claim_next_notification(
    test_db_engine,
):
    SessionFactory = sessionmaker(
        bind=test_db_engine,
        expire_on_commit=False,
    )

    user = User(
        email=f"concurrency-{uuid.uuid4()}@example.test"
    )

    setup_session = SessionFactory()
    lock_session = SessionFactory()
    worker_session = SessionFactory()

    try:
        setup_session.add(user)
        setup_session.flush()

        project = Project(
            owner_id=user.id,
            name="Notification Concurrency Test",
            plan="free",
        )
        setup_session.add(project)
        setup_session.flush()

        monitor = Monitor(
            project_id=project.id,
            name="Concurrency Test Monitor",
            url="https://example.test",
        )

        channel = AlertChannel(
            project_id=project.id,
            type="email",
            destination="concurrency@example.test",
            enabled=True,
        )

        setup_session.add_all([monitor, channel])
        setup_session.flush()

        incident = Incident(monitor_id=monitor.id)
        setup_session.add(incident)
        setup_session.flush()

        now = datetime.now(timezone.utc)

        event_a = NotificationEvent(
            incident_id=incident.id,
            channel_id=channel.id,
            event_type="incident_opened",
            status="pending",
            attempts=0,
            next_attempt_at=now - timedelta(minutes=2),
        )

        event_b = NotificationEvent(
            incident_id=incident.id,
            channel_id=channel.id,
            event_type="incident_resolved",
            status="pending",
            attempts=0,
            next_attempt_at=now - timedelta(minutes=1),
        )

        setup_session.add_all([event_a, event_b])
        setup_session.commit()

        event_a_id = event_a.id
        event_b_id = event_b.id

        # Worker 1 locks the oldest notification and keeps
        # its transaction open.
        locked_event = lock_session.scalars(
            select(NotificationEvent)
            .where(NotificationEvent.id == event_a_id)
            .with_for_update()
        ).one()

        assert locked_event.status == "pending"

        # Worker 2 must skip the locked notification and
        # claim the next available notification.
        claimed_event_id = _claim_next_notification(
            worker_session
        )

        assert claimed_event_id == event_b_id

        # Worker 1 still owns the lock; its notification
        # has not been changed by Worker 2.
        assert locked_event.status == "pending"

        saved_event_b = worker_session.get(
            NotificationEvent,
            event_b_id,
        )

        assert saved_event_b.status == "processing"
        assert saved_event_b.locked_at is not None

    finally:
        worker_session.close()
        lock_session.rollback()
        lock_session.close()

        # Remove only the records created by this test.
        cleanup_session = SessionFactory()

        try:
            if "project" in locals() and project.id is not None:
                cleanup_session.query(NotificationEvent).filter(
                    NotificationEvent.incident_id.in_(
                        select(Incident.id).where(
                            Incident.monitor_id.in_(
                                select(Monitor.id).where(
                                    Monitor.project_id == project.id
                                )
                            )
                        )
                    )
                ).delete(synchronize_session=False)

                cleanup_session.query(Incident).filter(
                    Incident.monitor_id.in_(
                        select(Monitor.id).where(
                            Monitor.project_id == project.id
                        )
                    )
                ).delete(synchronize_session=False)

                cleanup_session.query(Monitor).filter_by(
                    project_id=project.id
                ).delete(synchronize_session=False)

                cleanup_session.query(AlertChannel).filter_by(
                    project_id=project.id
                ).delete(synchronize_session=False)

                cleanup_session.query(Project).filter_by(
                    id=project.id
                ).delete(synchronize_session=False)

                cleanup_session.query(User).filter_by(
                    id=user.id
                ).delete(synchronize_session=False)

                cleanup_session.commit()
        finally:
            cleanup_session.close()
            setup_session.close()
