
import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest, LoginRequest


def test_register_normalizes_email():
    request = RegisterRequest(
        email="  USER@Example.com ",
        password="StrongPassword@123",
    )

    assert request.email == "user@example.com"


def test_register_rejects_invalid_email():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="invalid-email",
            password="StrongPassword@123",
        )


def test_register_rejects_short_password():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com",
            password="short",
        )


def test_register_rejects_password_over_128_characters():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com",
            password="A" * 129,
        )


def test_login_normalizes_email():
    request = LoginRequest(
        email="  USER@Example.com ",
        password="password",
    )

    assert request.email == "user@example.com"


def test_login_rejects_invalid_email():
    with pytest.raises(ValidationError):
        LoginRequest(
            email="invalid-email",
            password="password",
        )


def test_login_accepts_existing_short_password():
    request = LoginRequest(
        email="user@example.com",
        password="oldpass",
    )

    assert request.password == "oldpass"
