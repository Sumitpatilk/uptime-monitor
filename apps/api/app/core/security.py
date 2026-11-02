
from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import uuid

import jwt
from pwdlib import PasswordHash

from app.core.config import settings


# Argon2 password hashing
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a plain-text password using Argon2."""
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its stored hash."""
    return password_hasher.verify(plain_password, hashed_password)


# Access token functions
def create_access_token(
    user_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token for a user."""
    now = datetime.now(timezone.utc)
    expires_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )

    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate an access token. Return None if invalid."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "iat", "exp"]},
        )

        if payload.get("type") != "access":
            return None

        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            return None

        return payload

    except jwt.InvalidTokenError:
        return None


# Refresh token functions
def create_refresh_token(
    user_id: str,
    family_id: str | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    """
    Create a refresh JWT.

    Returns:
        A tuple containing (raw_token, family_id).
    """
    now = datetime.now(timezone.utc)

    token_family_id = family_id or str(uuid.uuid4())
    token_id = str(uuid.uuid4())

    expires_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=settings.refresh_token_expire_days)
    )

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": token_id,
        "family_id": token_family_id,
        "iat": now,
        "exp": expires_at,
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    return token, token_family_id


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a refresh token. Return None if invalid."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={
                "require": [
                    "sub",
                    "type",
                    "jti",
                    "family_id",
                    "iat",
                    "exp",
                ],
            },
        )

        if payload.get("type") != "refresh":
            return None

        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            return None

        # Validate token ID and family ID formats.
        uuid.UUID(payload["jti"])
        uuid.UUID(payload["family_id"])

        return payload

    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 hex digest of a raw refresh token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
