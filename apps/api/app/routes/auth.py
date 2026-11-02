from datetime import datetime, timezone
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.csrf import verify_request_origin
from app.core.dependencies import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.session import get_db
from app.models import RefreshToken, User
from app.schemas.auth import LoginRequest, RegisterRequest, UserRead


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"


def set_auth_cookies(response: Response, user_id: UUID) -> RefreshToken:
    """Create and set access and refresh HttpOnly cookies."""

    access_token = create_access_token(str(user_id))

    refresh_token, family_id = create_refresh_token(str(user_id))
    refresh_payload = decode_refresh_token(refresh_token)

    if refresh_payload is None:
        raise RuntimeError("Failed to create refresh token.")

    refresh_expires_at = datetime.fromtimestamp(
        refresh_payload["exp"],
        tz=timezone.utc,
    )

    stored_token = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(refresh_token),
        family_id=UUID(family_id),
        expires_at=refresh_expires_at,
    )

    db = None

    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/api/auth",
    )

    return stored_token


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )

    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
    )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_request_origin)],
)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    existing_user = db.scalar(
        select(User).where(User.email == payload.email)
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
    )

    db.add(user)

    try:
        db.flush()
        stored_token = set_auth_cookies(response, user.id)
        db.add(stored_token)
        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    response.headers["Cache-Control"] = "no-store"

    return user


@router.post(
    "/login",
    response_model=UserRead,
    dependencies=[Depends(verify_request_origin)],
)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(User.email == payload.email)
    )

    if (
        user is None
        or user.password_hash is None
        or not verify_password(payload.password, user.password_hash)
    ):
        raise authentication_error()

    stored_token = set_auth_cookies(response, user.id)
    db.add(stored_token)
    db.commit()

    response.headers["Cache-Control"] = "no-store"

    return user


@router.get("/me", response_model=UserRead)
def get_me(
    response: Response,
    current_user: User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store"
    return current_user


@router.post(
    "/refresh",
    dependencies=[Depends(verify_request_origin)],
)
def refresh_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required.",
        )

    payload = decode_refresh_token(raw_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    token_hash = hash_refresh_token(raw_token)

    stored_token = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )

    if stored_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not recognized.",
        )

    now = datetime.now(timezone.utc)

    if stored_token.revoked_at is not None:
        # A revoked token was reused: revoke its entire token family.
        db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == stored_token.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        db.commit()

        clear_auth_cookies(response)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. Please log in again.",
        )

    if (
        stored_token.user_id != UUID(payload["sub"])
        or stored_token.family_id != UUID(payload["family_id"])
        or stored_token.expires_at <= now
    ):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    user = db.get(User, stored_token.user_id)

    if user is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    # Revoke the old token before issuing its replacement.
    stored_token.revoked_at = now

    new_refresh_token, family_id = create_refresh_token(
        str(user.id),
        family_id=str(stored_token.family_id),
    )

    new_payload = decode_refresh_token(new_refresh_token)

    if new_payload is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create refresh token.",
        )

    new_stored_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_refresh_token),
        family_id=UUID(family_id),
        expires_at=datetime.fromtimestamp(
            new_payload["exp"],
            tz=timezone.utc,
        ),
    )

    db.add(new_stored_token)

    new_access_token = create_access_token(str(user.id))

    db.commit()

    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=new_access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=new_refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/api/auth",
    )

    response.headers["Cache-Control"] = "no-store"

    return {"message": "Session refreshed successfully."}


@router.post(
    "/logout",
    dependencies=[Depends(verify_request_origin)],
)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)

    if raw_token:
        stored_token = db.scalar(
            select(RefreshToken)
            .where(
                RefreshToken.token_hash == hash_refresh_token(raw_token)
            )
            .with_for_update()
        )

        if stored_token and stored_token.revoked_at is None:
            stored_token.revoked_at = datetime.now(timezone.utc)
            db.commit()

    clear_auth_cookies(response)
    response.headers["Cache-Control"] = "no-store"

    return {"message": "Logged out successfully."}