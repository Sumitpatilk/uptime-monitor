import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import (
    AlertChannel,
    Incident,
    Monitor,
    NotificationEvent,
    Project,
    User,
)
from app.services.check_runner import create_notification_events


def test_concurrent_notification_creation_creates_only_one_event(
    test_db_engine,
):
    SessionFactory = sessionmaker(
        bind=test_db_engine,
        expire_on_commit=False,
    )

    setup_session = SessionFactory()

    user = User(
        email=f"notification-race-{uuid.uuid4()}@example.test"
    )

    try:
        setup_session.add(user)
        setup_session.flush()

        project = Project(
            owner_id=user.id,
            name="Notification Race Test",
            plan="free",
        )
        setup_session.add(project)
        setup_session.flush()

        monitor = Monitor(
            project_id=project.id,
            name="Notification Race Monitor",
            url="https://example.test",
        )

        channel = AlertChannel(
            project_id=project.id,
            type="email",
            destination="race@example.test",
            enabled=True,
        )

        setup_session.add_all([monitor, channel])
        setup_session.flush()

        incident = Incident(
            monitor_id=monitor.id,
            state="open",
        )
        setup_session.add(incident)
        setup_session.commit()

        project_id = project.id
        monitor_id = monitor.id
        incident_id = incident.id

    except Exception:
        setup_session.rollback()
        raise
    finally:
        setup_session.close()

    barrier = Barrier(2)

    def create_event_concurrently():
        session = SessionFactory()

        try:
            current_monitor = session.get(Monitor, monitor_id)
            current_incident = session.get(Incident, incident_id)

            assert current_monitor is not None
            assert current_incident is not None

            # Start both database operations together.
            barrier.wait(timeout=15)

            create_notification_events(
                current_incident,
                current_monitor,
                "incident_opened",
                session,
            )

            session.commit()

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(create_event_concurrently)
                for _ in range(2)
            ]

            for future in futures:
                future.result(timeout=30)

        verification_session = SessionFactory()

        try:
            event_count = verification_session.scalar(
                select(func.count())
                .select_from(NotificationEvent)
                .where(
                    NotificationEvent.incident_id == incident_id,
                    NotificationEvent.event_type == "incident_opened",
                )
            )

            assert event_count == 1, (
                f"Expected exactly 1 notification event, found {event_count}"
            )
        finally:
            verification_session.close()

    finally:
        cleanup_session = SessionFactory()

        try:
            cleanup_session.query(NotificationEvent).filter(
                NotificationEvent.incident_id == incident_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Incident).filter_by(
                id=incident_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Monitor).filter_by(
                id=monitor_id
            ).delete(synchronize_session=False)

            cleanup_session.query(AlertChannel).filter_by(
                project_id=project_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Project).filter_by(
                id=project_id
            ).delete(synchronize_session=False)

            cleanup_session.query(User).filter_by(
                id=user.id
            ).delete(synchronize_session=False)

            cleanup_session.commit()

        except Exception:
            cleanup_session.rollback()
            raise
        finally:
            cleanup_session.close()
