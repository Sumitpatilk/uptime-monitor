
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import Project, User


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
        email=f"project-test-{uuid.uuid4()}@example.test",
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
        email=f"another-user-{uuid.uuid4()}@example.test",
        password_hash=hash_password("StrongPassword123!"),
    )

    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    return user


def test_projects_require_authentication(api_client):
    response = api_client.get("/api/projects")

    assert response.status_code == 401


def test_create_project_uses_authenticated_user(authenticated_client):
    client, user = authenticated_client

    response = client.post(
        "/api/projects",
        headers={"Origin": ORIGIN},
        json={
            "name": "My Secure Project",
            "owner_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "My Secure Project"
    assert response.json()["owner_id"] == str(user.id)


def test_list_projects_returns_only_owned_projects(
    authenticated_client,
    test_db_session,
    another_user,
):
    client, user = authenticated_client

    own_project = Project(
        owner_id=user.id,
        name="My Project",
        plan="free",
    )

    other_project = Project(
        owner_id=another_user.id,
        name="Other User Project",
        plan="free",
    )

    test_db_session.add_all([own_project, other_project])
    test_db_session.commit()

    response = client.get("/api/projects")

    assert response.status_code == 200

    project_names = [item["name"] for item in response.json()]

    assert "My Project" in project_names
    assert "Other User Project" not in project_names


def test_cannot_read_another_users_project(
    authenticated_client,
    test_db_session,
    another_user,
):
    client, _ = authenticated_client

    project = Project(
        owner_id=another_user.id,
        name="Private Project",
        plan="free",
    )

    test_db_session.add(project)
    test_db_session.commit()
    test_db_session.refresh(project)

    response = client.get(f"/api/projects/{project.id}")

    assert response.status_code == 404


def test_cannot_update_another_users_project(
    authenticated_client,
    test_db_session,
    another_user,
):
    client, _ = authenticated_client

    project = Project(
        owner_id=another_user.id,
        name="Private Project",
        plan="free",
    )

    test_db_session.add(project)
    test_db_session.commit()
    test_db_session.refresh(project)

    response = client.patch(
        f"/api/projects/{project.id}",
        headers={"Origin": ORIGIN},
        json={"name": "Hacked Project"},
    )

    assert response.status_code == 404
    assert project.name == "Private Project"


def test_cannot_delete_another_users_project(
    authenticated_client,
    test_db_session,
    another_user,
):
    client, _ = authenticated_client

    project = Project(
        owner_id=another_user.id,
        name="Private Project",
        plan="free",
    )

    test_db_session.add(project)
    test_db_session.commit()
    test_db_session.refresh(project)

    response = client.delete(
        f"/api/projects/{project.id}",
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 404

    assert test_db_session.get(Project, project.id) is not None


@pytest.mark.parametrize(
    "origin",
    [None, "https://untrusted.example"],
)
def test_create_project_rejects_untrusted_origin(
    authenticated_client,
    origin,
):
    client, _ = authenticated_client

    headers = {}
    if origin is not None:
        headers["Origin"] = origin

    response = client.post(
        "/api/projects",
        headers=headers,
        json={"name": "Blocked Project"},
    )

    assert response.status_code == 403
