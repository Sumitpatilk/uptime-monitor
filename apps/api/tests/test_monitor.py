
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import Monitor, Project, User


ORIGIN = "http://localhost:5173"
PUBLIC_URL = "https://example.com"


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
        email=f"monitor-test-{uuid.uuid4()}@example.test",
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
        email=f"another-monitor-user-{uuid.uuid4()}@example.test",
        password_hash=hash_password("StrongPassword123!"),
    )

    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    return user


@pytest.fixture
def own_project(test_db_session, authenticated_client):
    _, user = authenticated_client

    project = Project(
        owner_id=user.id,
        name="My Monitor Project",
        plan="free",
    )

    test_db_session.add(project)
    test_db_session.commit()
    test_db_session.refresh(project)

    return project


def test_monitors_require_authentication(api_client):
    project_id = uuid.uuid4()

    response = api_client.get(
        f"/api/projects/{project_id}/monitors"
    )

    assert response.status_code == 401


def test_create_monitor_in_owned_project(
    authenticated_client,
    own_project,
):
    client, _ = authenticated_client

    response = client.post(
        f"/api/projects/{own_project.id}/monitors",
        headers={"Origin": ORIGIN},
        json={
            "name": "Example Website",
            "url": PUBLIC_URL,
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Example Website"
    assert response.json()["project_id"] == str(own_project.id)


def test_list_monitors_in_owned_project(
    authenticated_client,
    own_project,
    test_db_session,
):
    client, _ = authenticated_client

    monitor = Monitor(
        project_id=own_project.id,
        name="Example Website",
        url=PUBLIC_URL,
    )

    test_db_session.add(monitor)
    test_db_session.commit()

    response = client.get(
        f"/api/projects/{own_project.id}/monitors"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Example Website"


def test_cannot_access_another_users_project_monitors(
    authenticated_client,
    another_user,
    test_db_session,
):
    client, _ = authenticated_client

    other_project = Project(
        owner_id=another_user.id,
        name="Private Project",
        plan="free",
    )

    test_db_session.add(other_project)
    test_db_session.commit()
    test_db_session.refresh(other_project)

    response = client.get(
        f"/api/projects/{other_project.id}/monitors"
    )

    assert response.status_code == 404


def test_cannot_update_another_users_project_monitor(
    authenticated_client,
    another_user,
    test_db_session,
):
    client, _ = authenticated_client

    other_project = Project(
        owner_id=another_user.id,
        name="Private Project",
        plan="free",
    )

    test_db_session.add(other_project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=other_project.id,
        name="Private Monitor",
        url=PUBLIC_URL,
    )

    test_db_session.add(monitor)
    test_db_session.commit()
    test_db_session.refresh(monitor)

    response = client.patch(
        f"/api/projects/{other_project.id}/monitors/{monitor.id}",
        headers={"Origin": ORIGIN},
        json={"name": "Hacked Monitor"},
    )

    assert response.status_code == 404
    assert monitor.name == "Private Monitor"


def test_cannot_delete_another_users_project_monitor(
    authenticated_client,
    another_user,
    test_db_session,
):
    client, _ = authenticated_client

    other_project = Project(
        owner_id=another_user.id,
        name="Private Project",
        plan="free",
    )

    test_db_session.add(other_project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=other_project.id,
        name="Private Monitor",
        url=PUBLIC_URL,
    )

    test_db_session.add(monitor)
    test_db_session.commit()
    test_db_session.refresh(monitor)

    response = client.delete(
        f"/api/projects/{other_project.id}/monitors/{monitor.id}",
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 404
    assert test_db_session.get(Monitor, monitor.id) is not None


@pytest.mark.parametrize(
    "origin",
    [None, "https://untrusted.example"],
)
def test_create_monitor_rejects_untrusted_origin(
    authenticated_client,
    own_project,
    origin,
):
    client, _ = authenticated_client

    headers = {}
    if origin is not None:
        headers["Origin"] = origin

    response = client.post(
        f"/api/projects/{own_project.id}/monitors",
        headers=headers,
        json={
            "name": "Blocked Monitor",
            "url": PUBLIC_URL,
        },
    )

    assert response.status_code == 403
