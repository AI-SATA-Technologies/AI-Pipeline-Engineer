"""API-key authentication (env-gated).

If ``config.API_KEYS`` is non-empty, protected endpoints require an ``X-API-Key``
request header matching one of the keys (several keys allow rotation). If it is
empty, the dependency is a no-op so the API stays open (backward-compatible
default; a warning is logged at startup). Comparisons are constant-time.
"""
import hmac

from fastapi import Header, HTTPException, status

import config


def _matches(candidate: str) -> bool:
    given = candidate.encode('utf-8')
    # Compare against every key (no early exit) so timing doesn't reveal which matched.
    hits = [hmac.compare_digest(given, k.encode('utf-8')) for k in config.API_KEYS]
    return any(hits)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency that enforces the X-API-Key header when keys are configured."""
    if not config.API_KEYS:
        return
    if not x_api_key or not _matches(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or missing API key',
            headers={'WWW-Authenticate': 'X-API-Key'},
        )
