import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import Incident, Monitor, Project, User


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
        email=f"incidents-api-{uuid.uuid4()}@example.test",
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
        email=f"other-incidents-{uuid.uuid4()}@example.test",
        password_hash=hash_password("StrongPassword123!"),
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture
def incident_project(test_db_session, authenticated_client):
    _, user = authenticated_client

    project = Project(
        owner_id=user.id,
        name="Incident API Project",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Incident API Monitor",
        url="https://example.com",
    )
    test_db_session.add(monitor)
    test_db_session.commit()
    test_db_session.refresh(monitor)

    return project, monitor


@pytest.fixture
def another_users_incident(test_db_session, another_user):
    project = Project(
        owner_id=another_user.id,
        name="Private Incident Project",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.flush()

    monitor = Monitor(
        project_id=project.id,
        name="Private Incident Monitor",
        url="https://example.com",
    )
    test_db_session.add(monitor)
    test_db_session.flush()

    incident = Incident(
        monitor_id=monitor.id,
        state="open",
        summary="Private incident",
    )
    test_db_session.add(incident)
    test_db_session.commit()
    test_db_session.refresh(incident)

    return project, incident


def create_incident(db, monitor, state="open", summary="Test incident"):
    incident = Incident(
        monitor_id=monitor.id,
        state=state,
        summary=summary,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def test_incidents_require_authentication(api_client):
    project_id = uuid.uuid4()
    incident_id = uuid.uuid4()

    list_response = api_client.get(
        f"/api/projects/{project_id}/incidents"
    )
    detail_response = api_client.get(
        f"/api/projects/{project_id}/incidents/{incident_id}"
    )

    assert list_response.status_code == 401
    assert detail_response.status_code == 401


def test_list_incidents_for_owned_project(
    authenticated_client,
    incident_project,
    test_db_session,
):
    client, _ = authenticated_client
    project, monitor = incident_project

    incident = create_incident(
        test_db_session,
        monitor,
        summary="Website unavailable",
    )

    response = client.get(
        f"/api/projects/{project.id}/incidents"
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == str(incident.id)
    assert data[0]["monitor_id"] == str(monitor.id)
    assert data[0]["state"] == "open"
    assert data[0]["summary"] == "Website unavailable"


def test_get_incident_detail(
    authenticated_client,
    incident_project,
    test_db_session,
):
    client, _ = authenticated_client
    project, monitor = incident_project

    incident = create_incident(
        test_db_session,
        monitor,
        summary="API recovered",
    )

    response = client.get(
        f"/api/projects/{project.id}/incidents/{incident.id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(incident.id)
    assert response.json()["summary"] == "API recovered"


def test_filter_incidents_by_state(
    authenticated_client,
    incident_project,
    test_db_session,
):
    client, _ = authenticated_client
    project, monitor = incident_project

    open_incident = create_incident(
        test_db_session,
        monitor,
        state="open",
    )
    create_incident(
        test_db_session,
        monitor,
        state="resolved",
    )

    response = client.get(
        f"/api/projects/{project.id}/incidents?state=open"
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == str(open_incident.id)
    assert data[0]["state"] == "open"


def test_incident_list_supports_pagination(
    authenticated_client,
    incident_project,
    test_db_session,
):
    client, _ = authenticated_client
    project, monitor = incident_project

    create_incident(test_db_session, monitor, state="resolved")
    create_incident(test_db_session, monitor, state="resolved")

    response = client.get(
        f"/api/projects/{project.id}/incidents?limit=1&offset=1"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_cannot_list_another_users_incidents(
    authenticated_client,
    another_users_incident,
):
    client, _ = authenticated_client
    project, _ = another_users_incident

    response = client.get(
        f"/api/projects/{project.id}/incidents"
    )

    assert response.status_code == 404


def test_cannot_get_another_users_incident(
    authenticated_client,
    another_users_incident,
):
    client, _ = authenticated_client
    project, incident = another_users_incident

    response = client.get(
        f"/api/projects/{project.id}/incidents/{incident.id}"
    )

    assert response.status_code == 404


def test_get_unknown_incident_returns_404(
    authenticated_client,
    incident_project,
):
    client, _ = authenticated_client
    project, _ = incident_project

    response = client.get(
        f"/api/projects/{project.id}/incidents/{uuid.uuid4()}"
    )

    assert response.status_code == 404


def test_invalid_incident_state_filter_returns_422(
    authenticated_client,
    incident_project,
):
    client, _ = authenticated_client
    project, _ = incident_project

    response = client.get(
        f"/api/projects/{project.id}/incidents?state=invalid"
    )

    assert response.status_code == 422


def test_health_live_returns_alive(api_client):
    response = api_client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready_returns_503_when_database_is_unavailable(
    api_client,
    monkeypatch,
):
    def fail_database_connection():
        raise SQLAlchemyError("Database unavailable")

    monkeypatch.setattr(
        "app.main.engine.connect",
        fail_database_connection,
    )

    response = api_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "status": "not_ready",
        "database": "unavailable",
    }
