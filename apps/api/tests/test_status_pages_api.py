import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import AuditEvent, CheckResult, Incident, Monitor, Project, StatusPage, User


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
        email=f"status-pages-{uuid.uuid4()}@example.test",
        password_hash=hash_password("StrongPassword123!"),
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    token = create_access_token(str(user.id))
    api_client.cookies.set("access_token", token, path="/")

    return api_client, user


@pytest.fixture
def status_project(test_db_session, authenticated_client):
    _, user = authenticated_client

    project = Project(
        owner_id=user.id,
        name="Status Page Project",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.commit()
    test_db_session.refresh(project)

    return project


@pytest.fixture
def another_users_project(test_db_session):
    user = User(
        email=f"other-status-{uuid.uuid4()}@example.test",
        password_hash=hash_password("StrongPassword123!"),
    )
    test_db_session.add(user)
    test_db_session.flush()

    project = Project(
        owner_id=user.id,
        name="Private Status Project",
        plan="free",
    )
    test_db_session.add(project)
    test_db_session.commit()
    test_db_session.refresh(project)

    return project


def create_status_page(db, project, **overrides):
    values = {
        "slug": f"status-{uuid.uuid4().hex[:12]}",
        "visibility": "public",
        "enabled": True,
    }
    values.update(overrides)

    page = StatusPage(
        project_id=project.id,
        **values,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def test_status_page_routes_require_authentication(api_client):
    project_id = uuid.uuid4()
    page_id = uuid.uuid4()

    response = api_client.get(
        f"/api/projects/{project_id}/status-pages"
    )
    assert response.status_code == 401

    response = api_client.post(
        f"/api/projects/{project_id}/status-pages",
        json={"slug": "public-status"},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 401

    response = api_client.patch(
        f"/api/projects/{project_id}/status-pages/{page_id}",
        json={"enabled": True},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 401

    response = api_client.delete(
        f"/api/projects/{project_id}/status-pages/{page_id}",
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 401


def test_create_status_page_normalizes_slug(
    authenticated_client,
    status_project,
    test_db_session,
):
    client, user = authenticated_client

    response = client.post(
        f"/api/projects/{status_project.id}/status-pages",
        json={"slug": "  My-Status-Page  "},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 201
    assert response.json()["slug"] == "my-status-page"
    assert response.json()["project_id"] == str(status_project.id)
    assert response.json()["visibility"] == "public"
    assert response.json()["enabled"] is False

    event = test_db_session.query(AuditEvent).filter_by(
        project_id=status_project.id,
        action="status_page.created",
    ).one()
    assert event.actor_id == user.id


def test_list_status_pages_for_owned_project(
    authenticated_client,
    status_project,
    test_db_session,
):
    client, _ = authenticated_client
    page = create_status_page(test_db_session, status_project)

    response = client.get(
        f"/api/projects/{status_project.id}/status-pages"
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == str(page.id)
    assert data[0]["slug"] == page.slug


def test_update_status_page(
    authenticated_client,
    status_project,
    test_db_session,
):
    client, user = authenticated_client
    page = create_status_page(
        test_db_session,
        status_project,
        enabled=False,
    )

    response = client.patch(
        f"/api/projects/{status_project.id}/status-pages/{page.id}",
        json={
            "slug": "updated-status",
            "visibility": "private",
            "enabled": True,
        },
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["slug"] == "updated-status"
    assert data["visibility"] == "private"
    assert data["enabled"] is True

    event = test_db_session.query(AuditEvent).filter_by(
        project_id=status_project.id,
        action="status_page.updated",
    ).one()
    assert event.actor_id == user.id


def test_update_status_page_rejects_empty_payload(
    authenticated_client,
    status_project,
    test_db_session,
):
    client, _ = authenticated_client
    page = create_status_page(test_db_session, status_project)

    response = client.patch(
        f"/api/projects/{status_project.id}/status-pages/{page.id}",
        json={},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 400


def test_delete_status_page(
    authenticated_client,
    status_project,
    test_db_session,
):
    client, user = authenticated_client
    page = create_status_page(test_db_session, status_project)

    response = client.delete(
        f"/api/projects/{status_project.id}/status-pages/{page.id}",
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 204

    list_response = client.get(
        f"/api/projects/{status_project.id}/status-pages"
    )
    assert list_response.status_code == 200
    assert list_response.json() == []

    event = test_db_session.query(AuditEvent).filter_by(
        project_id=status_project.id,
        action="status_page.deleted",
    ).one()
    assert event.actor_id == user.id


@pytest.mark.parametrize(
    "slug",
    [
        "ab",
        "-invalid",
        "invalid-",
        "invalid slug",
        "invalid_slug",
        "invalid.slug",
    ],
)
def test_create_status_page_rejects_invalid_slug(
    authenticated_client,
    status_project,
    slug,
):
    client, _ = authenticated_client

    response = client.post(
        f"/api/projects/{status_project.id}/status-pages",
        json={"slug": slug},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 422


def test_duplicate_status_page_slug_returns_conflict(
    authenticated_client,
    status_project,
    test_db_session,
):
    client, _ = authenticated_client
    create_status_page(
        test_db_session,
        status_project,
        slug="duplicate-status",
    )

    response = client.post(
        f"/api/projects/{status_project.id}/status-pages",
        json={"slug": "duplicate-status"},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 409

    event_count = test_db_session.query(AuditEvent).filter_by(
        project_id=status_project.id,
        action="status_page.created",
    ).count()
    assert event_count == 0


def test_cannot_list_another_users_status_pages(
    authenticated_client,
    another_users_project,
):
    client, _ = authenticated_client

    response = client.get(
        f"/api/projects/{another_users_project.id}/status-pages"
    )

    assert response.status_code == 404


def test_public_status_page_requires_enabled_public_page(
    api_client,
    status_project,
    test_db_session,
):
    disabled_page = create_status_page(
        test_db_session,
        status_project,
        enabled=False,
    )

    private_page = create_status_page(
        test_db_session,
        status_project,
        visibility="private",
    )

    disabled_response = api_client.get(
        f"/api/status/{disabled_page.slug}"
    )
    private_response = api_client.get(
        f"/api/status/{private_page.slug}"
    )

    assert disabled_response.status_code == 404
    assert private_response.status_code == 404


def test_public_status_page_returns_latest_monitor_check_without_sensitive_data(
    api_client,
    status_project,
    test_db_session,
):
    page = create_status_page(
        test_db_session,
        status_project,
    )

    monitor = Monitor(
        project_id=status_project.id,
        name="Public Website",
        url="https://internal-example.test/private-path",
        enabled=True,
    )
    test_db_session.add(monitor)
    test_db_session.flush()

    older_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    latest_time = datetime.now(timezone.utc)

    test_db_session.add_all(
        [
            CheckResult(
                monitor_id=monitor.id,
                checked_at=older_time,
                status="down",
                status_code=500,
                latency_ms=900,
                error_code="internal_old_error",
            ),
            CheckResult(
                monitor_id=monitor.id,
                checked_at=latest_time,
                status="up",
                status_code=200,
                latency_ms=120,
                error_code=None,
            ),
        ]
    )
    test_db_session.commit()

    response = api_client.get(f"/api/status/{page.slug}")

    assert response.status_code == 200
    data = response.json()

    assert data["slug"] == page.slug
    assert data["overall_status"] == "operational"
    assert len(data["monitors"]) == 1

    public_monitor = data["monitors"][0]
    assert public_monitor["name"] == "Public Website"
    assert public_monitor["status"] == "up"
    assert public_monitor["latency_ms"] == 120
    assert set(public_monitor.keys()) == {
        "name",
        "status",
        "last_checked_at",
        "latency_ms",
    }

    response_text = response.text
    assert "internal-example.test" not in response_text
    assert "internal_old_error" not in response_text
    assert "status_code" not in response_text
    assert data["incidents"] == []


def test_public_status_page_reports_outage_and_open_incident(
    api_client,
    status_project,
    test_db_session,
):
    page = create_status_page(test_db_session, status_project)

    monitor = Monitor(
        project_id=status_project.id,
        name="Unavailable API",
        url="https://internal-api.example.test",
        enabled=True,
    )
    test_db_session.add(monitor)
    test_db_session.flush()

    test_db_session.add(
        CheckResult(
            monitor_id=monitor.id,
            status="down",
            status_code=503,
            latency_ms=1000,
            error_code="internal_connection_error",
        )
    )

    test_db_session.add(
        Incident(
            monitor_id=monitor.id,
            state="open",
            summary="Internal incident details",
        )
    )
    test_db_session.commit()

    response = api_client.get(f"/api/status/{page.slug}")

    assert response.status_code == 200
    data = response.json()

    assert data["overall_status"] == "major_outage"
    assert data["monitors"][0]["status"] == "down"
    assert len(data["incidents"]) == 1
    assert data["incidents"][0]["state"] == "open"

    assert "internal-api.example.test" not in response.text
    assert "internal_connection_error" not in response.text
    assert "Internal incident details" not in response.text


def test_public_status_page_returns_unknown_without_checks(
    api_client,
    status_project,
    test_db_session,
):
    page = create_status_page(test_db_session, status_project)

    monitor = Monitor(
        project_id=status_project.id,
        name="New Monitor",
        url="https://example.test",
        enabled=True,
    )
    test_db_session.add(monitor)
    test_db_session.commit()

    response = api_client.get(f"/api/status/{page.slug}")

    assert response.status_code == 200
    assert response.json()["overall_status"] == "unknown"
    assert response.json()["monitors"][0]["status"] == "unknown"


def test_unknown_public_status_page_returns_404(api_client):
    response = api_client.get("/api/status/nonexistent-status-page")

    assert response.status_code == 404
