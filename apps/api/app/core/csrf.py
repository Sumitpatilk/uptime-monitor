from fastapi import HTTPException, Request, status

from app.core.config import settings


def verify_request_origin(request: Request) -> None:
    """
    Validate the Origin header for state-changing requests.
    Reject missing or untrusted origins.
    """

    origin = request.headers.get("origin")

    if not origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing request origin.",
        )

    allowed_origins = set(settings.cors_origin_list)

    if origin not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Untrusted request origin.",
        )