"""API-key authentication (env-gated).

If ``config.API_KEY`` is set, protected endpoints require a matching
``X-API-Key`` request header. If it is empty, the dependency is a no-op so the
API stays open (backward-compatible default). The comparison is constant-time.
"""
import hmac

from fastapi import Header, HTTPException, status

from config import API_KEY


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency that enforces the X-API-Key header when API_KEY is set."""
    if not API_KEY:
        return
    if not x_api_key or not hmac.compare_digest(
        x_api_key.encode('utf-8'), API_KEY.encode('utf-8')
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or missing API key',
            headers={'WWW-Authenticate': 'X-API-Key'},
        )
