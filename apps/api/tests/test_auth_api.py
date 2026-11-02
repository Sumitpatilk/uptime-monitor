import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password, hash_refresh_token
from app.db.session import get_db
from app.main import app
from app.models import RefreshToken, User


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
def test_user(test_db_session):
    user = User(
        email=f"auth-test-{uuid.uuid4()}@example.test",
        password_hash=hash_password("StrongPassword123!"),
    )

    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    return user


def test_register_user(api_client, test_db_session):
    response = api_client.post(
        "/api/auth/register",
        headers={"Origin": ORIGIN},
        json={
            "email": "NewUser@example.test",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "newuser@example.test"

    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies

    user = test_db_session.scalar(
        select(User).where(User.email == "newuser@example.test")
    )

    assert user is not None
    assert user.password_hash != "StrongPassword123!"
    assert test_db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id
        )
    ) is not None


def test_duplicate_registration_returns_conflict(api_client):
    payload = {
        "email": "duplicate@example.test",
        "password": "StrongPassword123!",
    }

    first = api_client.post(
        "/api/auth/register",
        headers={"Origin": ORIGIN},
        json=payload,
    )

    second = api_client.post(
        "/api/auth/register",
        headers={"Origin": ORIGIN},
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_login_success(api_client, test_user):
    response = api_client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={
            "email": test_user.email,
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == test_user.email
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies


def test_login_invalid_password(api_client, test_user):
    response = api_client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={
            "email": test_user.email,
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_current_user_requires_authentication(api_client):
    response = api_client.get("/api/auth/me")

    assert response.status_code == 401


def test_refresh_rotates_token(api_client):
    register_response = api_client.post(
        "/api/auth/register",
        headers={"Origin": ORIGIN},
        json={
            "email": "refresh@example.test",
            "password": "StrongPassword123!",
        },
    )

    assert register_response.status_code == 201

    old_token = api_client.cookies.get("refresh_token")
    assert old_token is not None

    old_hash = hash_refresh_token(old_token)

    response = api_client.post(
        "/api/auth/refresh",
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 200

    new_token = api_client.cookies.get("refresh_token")

    assert new_token is not None
    assert new_token != old_token


    assert old_hash != hash_refresh_token(new_token)


def test_logout_clears_auth_cookies(api_client):
    register_response = api_client.post(
        "/api/auth/register",
        headers={"Origin": ORIGIN},
        json={
            "email": "logout@example.test",
            "password": "StrongPassword123!",
        },
    )

    assert register_response.status_code == 201

    response = api_client.post(
        "/api/auth/logout",
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 200

    me_response = api_client.get("/api/auth/me")
    assert me_response.status_code == 401


def test_register_rejects_missing_origin(api_client):
    response = api_client.post(
        "/api/auth/register",
        json={
            "email": "csrf@example.test",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 403