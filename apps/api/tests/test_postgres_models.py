import uuid

from sqlalchemy import select

from app.models.entities import Monitor, Project, User


def test_user_project_monitor_relationships(test_db_session):
    user = User(
        email=f"integration-{uuid.uuid4()}@example.test"
    )
    test_db_session.add(user)
    test_db_session.flush()

    project = Project(
        owner_id=user.id,
        name="Integration Test Project",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Integration Test Monitor",
        url="https://example.test",
        interval_seconds=60,
        timeout_seconds=10,
        expected_status=200,
        enabled=True,
    )
    test_db_session.add(monitor)
    test_db_session.commit()

    saved_user = test_db_session.scalar(
        select(User).where(User.id == user.id)
    )
    saved_project = test_db_session.scalar(
        select(Project).where(Project.id == project.id)
    )
    saved_monitor = test_db_session.scalar(
        select(Monitor).where(Monitor.id == monitor.id)
    )

    assert saved_user is not None
    assert saved_project.owner_id == saved_user.id
    assert saved_monitor.project_id == saved_project.id
    assert saved_monitor.url == "https://example.test"
