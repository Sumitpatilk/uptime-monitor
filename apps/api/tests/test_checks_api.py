
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import CheckResult, Monitor, Project, User


ORIGIN = "http://localhost:5173"


@pytest.fixture
def api_client(test_db_session):
    def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def authenticated_client(api_client, test_db_session):
    user = User(
        email=f"checks-test-{uuid.uuid4()}@example.test",
        password_hash=hash_password("StrongPassword123!"),
    )

    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    token = create_access_token(str(user.id))
    api_client.cookies.set("access_token", token, path="/")

    return api_client, user


@pytest.fixture
def another_user(test_db_session):
    user = User(
        email=f"another-checks-user-{uuid.uuid4()}@example.test",
        password_hash=hash_password("StrongPassword123!"),
    )

    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    return user


@pytest.fixture
def own_monitor(test_db_session, authenticated_client):
    _, user = authenticated_client

    project = Project(
        owner_id=user.id,
        name="Checks Test Project",
        plan="free",
    )

    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Checks Test Monitor",
        url="https://example.com",
    )

    test_db_session.add(monitor)
    test_db_session.commit()
    test_db_session.refresh(monitor)

    return project, monitor


@pytest.fixture
def another_users_monitor(test_db_session, another_user):
    project = Project(
        owner_id=another_user.id,
        name="Private Checks Project",
        plan="free",
    )

    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Private Monitor",
        url="https://example.com",
    )

    test_db_session.add(monitor)
    test_db_session.commit()
    test_db_session.refresh(monitor)

    return project, monitor


def test_checks_require_authentication(api_client):
    project_id = uuid.uuid4()
    monitor_id = uuid.uuid4()

    history_response = api_client.get(
        f"/api/projects/{project_id}/monitors/{monitor_id}/checks"
    )

    check_response = api_client.post(
        f"/api/projects/{project_id}/monitors/{monitor_id}/check",
        headers={"Origin": ORIGIN},
    )

    assert history_response.status_code == 401
    assert check_response.status_code == 401


def test_get_check_history_for_owned_monitor(
    authenticated_client,
    own_monitor,
    test_db_session,
):
    client, _ = authenticated_client
    project, monitor = own_monitor

    check = CheckResult(
        monitor_id=monitor.id,
        checked_at=datetime.now(timezone.utc),
        status="up",
        status_code=200,
        latency_ms=120,
        error_code=None,
    )

    test_db_session.add(check)
    test_db_session.commit()

    response = client.get(
        f"/api/projects/{project.id}/monitors/{monitor.id}/checks"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["monitor_id"] == str(monitor.id)
    assert data["count"] == 1
    assert data["checks"][0]["status"] == "up"
    assert data["checks"][0]["status_code"] == 200


def test_cannot_get_another_users_check_history(
    authenticated_client,
    another_users_monitor,
):
    client, _ = authenticated_client
    project, monitor = another_users_monitor

    response = client.get(
        f"/api/projects/{project.id}/monitors/{monitor.id}/checks"
    )

    assert response.status_code == 404


@patch("app.routes.checks.execute_monitor_check")
def test_run_check_for_owned_monitor(
    mock_execute,
    authenticated_client,
    own_monitor,
):
    client, _ = authenticated_client
    project, monitor = own_monitor

    mock_execute.return_value = CheckResult(
        id=uuid.uuid4(),
        monitor_id=monitor.id,
        checked_at=datetime.now(timezone.utc),
        status="up",
        status_code=200,
        latency_ms=100,
        error_code=None,
    )

    response = client.post(
        f"/api/projects/{project.id}/monitors/{monitor.id}/check",
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 201
    assert response.json()["monitor_id"] == str(monitor.id)
    assert response.json()["status"] == "up"
    mock_execute.assert_called_once()


@patch("app.routes.checks.execute_monitor_check")
def test_cannot_run_check_for_another_users_monitor(
    mock_execute,
    authenticated_client,
    another_users_monitor,
):
    client, _ = authenticated_client
    project, monitor = another_users_monitor

    response = client.post(
        f"/api/projects/{project.id}/monitors/{monitor.id}/check",
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 404
    mock_execute.assert_not_called()


@pytest.mark.parametrize(
    "origin",
    [None, "https://untrusted.example"],
)
def test_run_check_rejects_untrusted_origin(
    authenticated_client,
    own_monitor,
    origin,
):
    client, _ = authenticated_client
    project, monitor = own_monitor

    headers = {}
    if origin is not None:
        headers["Origin"] = origin

    response = client.post(
        f"/api/projects/{project.id}/monitors/{monitor.id}/check",
        headers=headers,
    )

    assert response.status_code == 403
