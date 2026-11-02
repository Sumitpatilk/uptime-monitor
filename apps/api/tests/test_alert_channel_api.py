import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models.entities import Project, User


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
def test_project(test_db_session):
    user = User(
        email=f"api-test-{uuid.uuid4()}@example.test"
    )
    test_db_session.add(user)
    test_db_session.flush()

    project = Project(
        owner_id=user.id,
        name="Alert Channel API Test Project",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.commit()
    test_db_session.refresh(project)

    return project


def test_create_alert_channel(api_client, test_project):
    response = api_client.post(
        f"/api/projects/{test_project.id}/alert-channels",
        json={
            "type": "email",
            "destination": "alerts@example.test",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["project_id"] == str(test_project.id)
    assert data["type"] == "email"
    assert data["destination"] == "alerts@example.test"
    assert data["enabled"] is True


def test_create_alert_channel_normalizes_email(api_client, test_project):
    response = api_client.post(
        f"/api/projects/{test_project.id}/alert-channels",
        json={
            "type": "email",
            "destination": "ALERTS@EXAMPLE.TEST",
        },
    )

    assert response.status_code == 201
    assert response.json()["destination"] == "alerts@example.test"


def test_list_alert_channels(api_client, test_project):
    api_client.post(
        f"/api/projects/{test_project.id}/alert-channels",
        json={
            "type": "email",
            "destination": "alerts@example.test",
        },
    )

    response = api_client.get(
        f"/api/projects/{test_project.id}/alert-channels"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["destination"] == "alerts@example.test"


def test_duplicate_alert_channel_returns_conflict(api_client, test_project):
    endpoint = f"/api/projects/{test_project.id}/alert-channels"
    payload = {
        "type": "email",
        "destination": "alerts@example.test",
    }

    first_response = api_client.post(endpoint, json=payload)
    second_response = api_client.post(endpoint, json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "This email alert channel already exists."
    )


def test_update_alert_channel_enabled_status(api_client, test_project):
    endpoint = f"/api/projects/{test_project.id}/alert-channels"

    create_response = api_client.post(
        endpoint,
        json={
            "type": "email",
            "destination": "alerts@example.test",
        },
    )
    channel_id = create_response.json()["id"]

    update_response = api_client.patch(
        f"{endpoint}/{channel_id}",
        json={"enabled": False},
    )

    assert update_response.status_code == 200
    assert update_response.json()["enabled"] is False


def test_delete_alert_channel(api_client, test_project):
    endpoint = f"/api/projects/{test_project.id}/alert-channels"

    create_response = api_client.post(
        endpoint,
        json={
            "type": "email",
            "destination": "alerts@example.test",
        },
    )
    channel_id = create_response.json()["id"]

    delete_response = api_client.delete(
        f"{endpoint}/{channel_id}"
    )

    assert delete_response.status_code == 204

    list_response = api_client.get(endpoint)
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_missing_project_returns_404(api_client):
    response = api_client.get(
        f"/api/projects/{uuid.uuid4()}/alert-channels"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."


def test_missing_alert_channel_returns_404(api_client, test_project):
    response = api_client.patch(
        f"/api/projects/{test_project.id}/alert-channels/{uuid.uuid4()}",
        json={"enabled": False},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Alert channel not found."
