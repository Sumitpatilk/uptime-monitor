
from datetime import timedelta
from uuid import uuid4

import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_refresh_token,
    hash_password,
    verify_password,
)

def test_hash_password_returns_hash():
    password = "TestPassword@123"

    hashed_password = hash_password(password)

    assert hashed_password
    assert hashed_password != password


def test_verify_password_accepts_correct_password():
    password = "TestPassword@123"
    hashed_password = hash_password(password)

    assert verify_password(password, hashed_password) is True


def test_verify_password_rejects_wrong_password():
    hashed_password = hash_password("TestPassword@123")

    assert verify_password("WrongPassword", hashed_password) is False


def test_create_access_token_returns_valid_token():
    user_id = str(uuid4())

    token = create_access_token(user_id)

    assert isinstance(token, str)
    assert token


def test_decode_access_token_returns_correct_user():
    user_id = str(uuid4())

    token = create_access_token(user_id)
    payload = decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["type"] == "access"
    assert "iat" in payload
    assert "exp" in payload


def test_decode_access_token_rejects_invalid_token():
    assert decode_access_token("invalid.token.value") is None


def test_decode_access_token_rejects_expired_token():
    user_id = str(uuid4())

    token = create_access_token(
        user_id,
        expires_delta=timedelta(seconds=-1),
    )

    assert decode_access_token(token) is None


def test_decode_access_token_rejects_refresh_token_type():
    user_id = str(uuid4())

    token = jwt.encode(
        {
            "sub": user_id,
            "type": "refresh",
            "iat": 1,
            "exp": 4102444800,
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    assert decode_access_token(token) is None


def test_decode_access_token_rejects_wrong_signature():
    user_id = str(uuid4())

    token = jwt.encode(
        {
            "sub": user_id,
            "type": "access",
            "iat": 1,
            "exp": 4102444800,
        },
        "incorrect-test-secret",
        algorithm=settings.jwt_algorithm,
    )

    assert decode_access_token(token) is None


def test_create_refresh_token_returns_valid_token():
    user_id = str(uuid4())

    token, family_id = create_refresh_token(user_id)

    assert isinstance(token, str)
    assert token
    assert family_id


def test_decode_refresh_token_returns_correct_claims():
    user_id = str(uuid4())

    token, family_id = create_refresh_token(user_id)
    payload = decode_refresh_token(token)

    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"
    assert payload["family_id"] == family_id
    assert "jti" in payload
    assert "iat" in payload
    assert "exp" in payload


def test_decode_refresh_token_rejects_invalid_token():
    assert decode_refresh_token("invalid.token.value") is None


def test_decode_refresh_token_rejects_expired_token():
    user_id = str(uuid4())

    token, _ = create_refresh_token(
        user_id,
        expires_delta=timedelta(seconds=-1),
    )

    assert decode_refresh_token(token) is None


def test_decode_refresh_token_rejects_access_token():
    user_id = str(uuid4())

    token = create_access_token(user_id)

    assert decode_refresh_token(token) is None


def test_hash_refresh_token_returns_sha256_hash():
    token, _ = create_refresh_token(str(uuid4()))

    hashed_token = hash_refresh_token(token)

    assert len(hashed_token) == 64
    assert hashed_token != token
    assert hash_refresh_token(token) == hashed_token


def test_refresh_token_rotation_can_preserve_family_id():
    user_id = str(uuid4())

    first_token, family_id = create_refresh_token(user_id)

    second_token, second_family_id = create_refresh_token(
        user_id,
        family_id=family_id,
    )

    assert first_token != second_token
    assert second_family_id == family_id

    first_payload = decode_refresh_token(first_token)
    second_payload = decode_refresh_token(second_token)

    assert first_payload is not None
    assert second_payload is not None
    assert first_payload["jti"] != second_payload["jti"]
