
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.entities import AlertChannel, Project, User


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
        email=f"alert-test-{uuid.uuid4()}@example.test",
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
        email=f"another-alert-user-{uuid.uuid4()}@example.test",
        password_hash=hash_password("StrongPassword123!"),
    )

    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    return user


@pytest.fixture
def test_project(test_db_session, authenticated_client):
    _, user = authenticated_client

    project = Project(
        owner_id=user.id,
        name="Alert Channel API Test Project",
        plan="free",
    )

    test_db_session.add(project)
    test_db_session.commit()
    test_db_session.refresh(project)

    return project


@pytest.fixture
def another_users_project(test_db_session, another_user):
    project = Project(
        owner_id=another_user.id,
        name="Another User Alert Project",
        plan="free",
    )

    test_db_session.add(project)
    test_db_session.commit()
    test_db_session.refresh(project)

    return project


def create_channel(client, project_id):
    return client.post(
        f"/api/projects/{project_id}/alert-channels",
        headers={"Origin": ORIGIN},
        json={
            "type": "email",
            "destination": "alerts@example.test",
        },
    )



def test_alert_channels_require_authentication(api_client):
    response = api_client.get(
        f"/api/projects/{uuid.uuid4()}/alert-channels"
    )

    assert response.status_code == 401



def test_create_alert_channel(authenticated_client, test_project):
    client, _ = authenticated_client

    response = create_channel(client, test_project.id)

    assert response.status_code == 201

    data = response.json()
    assert data["project_id"] == str(test_project.id)
    assert data["type"] == "email"
    assert data["destination"] == "alerts@example.test"
    assert data["enabled"] is True


def test_create_alert_channel_normalizes_email(
    authenticated_client,
    test_project,
):
    client, _ = authenticated_client

    response = client.post(
        f"/api/projects/{test_project.id}/alert-channels",
        headers={"Origin": ORIGIN},
        json={
            "type": "email",
            "destination": "ALERTS@EXAMPLE.TEST",
        },
    )

    assert response.status_code == 201
    assert response.json()["destination"] == "alerts@example.test"


def test_list_alert_channels(authenticated_client, test_project):
    client, _ = authenticated_client

    create_channel(client, test_project.id)

    response = client.get(
        f"/api/projects/{test_project.id}/alert-channels"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["destination"] == "alerts@example.test"


def test_duplicate_alert_channel_returns_conflict(
    authenticated_client,
    test_project,
):
    client, _ = authenticated_client
    endpoint = f"/api/projects/{test_project.id}/alert-channels"

    first_response = create_channel(client, test_project.id)
    second_response = create_channel(client, test_project.id)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "This email alert channel already exists."
    )


def test_update_alert_channel_enabled_status(
    authenticated_client,
    test_project,
):
    client, _ = authenticated_client
    endpoint = f"/api/projects/{test_project.id}/alert-channels"

    create_response = create_channel(client, test_project.id)
    channel_id = create_response.json()["id"]

    update_response = client.patch(
        f"{endpoint}/{channel_id}",
        headers={"Origin": ORIGIN},
        json={"enabled": False},
    )

    assert update_response.status_code == 200
    assert update_response.json()["enabled"] is False


def test_delete_alert_channel(authenticated_client, test_project):
    client, _ = authenticated_client
    endpoint = f"/api/projects/{test_project.id}/alert-channels"

    create_response = create_channel(client, test_project.id)
    channel_id = create_response.json()["id"]

    delete_response = client.delete(
        f"{endpoint}/{channel_id}",
        headers={"Origin": ORIGIN},
    )

    assert delete_response.status_code == 204

    list_response = client.get(endpoint)
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_cannot_access_another_users_alert_channels(
    authenticated_client,
    another_users_project,
):
    client, _ = authenticated_client

    response = client.get(
        f"/api/projects/{another_users_project.id}/alert-channels"
    )

    assert response.status_code == 404


def test_cannot_create_alert_channel_for_another_users_project(
    authenticated_client,
    another_users_project,
):
    client, _ = authenticated_client

    response = create_channel(client, another_users_project.id)

    assert response.status_code == 404


def test_cannot_update_another_users_alert_channel(
    authenticated_client,
    test_db_session,
    another_users_project,
):
    client, _ = authenticated_client

    channel = AlertChannel(
        project_id=another_users_project.id,
        type="email",
        destination="private@example.test",
        enabled=True,
    )

    test_db_session.add(channel)
    test_db_session.commit()
    test_db_session.refresh(channel)

    response = client.patch(
        f"/api/projects/{another_users_project.id}/alert-channels/{channel.id}",
        headers={"Origin": ORIGIN},
        json={"enabled": False},
    )

    assert response.status_code == 404
    assert channel.enabled is True


def test_cannot_delete_another_users_alert_channel(
    authenticated_client,
    test_db_session,
    another_users_project,
):
    client, _ = authenticated_client

    channel = AlertChannel(
        project_id=another_users_project.id,
        type="email",
        destination="private@example.test",
        enabled=True,
    )

    test_db_session.add(channel)
    test_db_session.commit()
    test_db_session.refresh(channel)

    response = client.delete(
        f"/api/projects/{another_users_project.id}/alert-channels/{channel.id}",
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 404
    assert test_db_session.get(AlertChannel, channel.id) is not None


def test_missing_project_returns_404(authenticated_client):
    client, _ = authenticated_client

    response = client.get(
        f"/api/projects/{uuid.uuid4()}/alert-channels"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."


def test_missing_alert_channel_returns_404(
    authenticated_client,
    test_project,
):
    client, _ = authenticated_client

    response = client.patch(
        f"/api/projects/{test_project.id}/alert-channels/{uuid.uuid4()}",
        headers={"Origin": ORIGIN},
        json={"enabled": False},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Alert channel not found."


@pytest.mark.parametrize(
    "origin",
    [None, "https://untrusted.example"],
)
def test_create_alert_channel_rejects_untrusted_origin(
    authenticated_client,
    test_project,
    origin,
):
    client, _ = authenticated_client

    headers = {}
    if origin is not None:
        headers["Origin"] = origin

    response = client.post(
        f"/api/projects/{test_project.id}/alert-channels",
        headers=headers,
        json={
            "type": "email",
            "destination": "alerts@example.test",
        },
    )

    assert response.status_code == 403
