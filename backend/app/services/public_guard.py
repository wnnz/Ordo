from __future__ import annotations

import hashlib
import logging

import redis
import redis.asyncio as async_redis
from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.services.system_settings import runtime_values

logger = logging.getLogger(__name__)
RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {current, redis.call('TTL', KEYS[1])}
"""


def scope_limit(scope: str, values: dict[str, int] | None = None) -> int:
    settings = get_settings()
    values = values or {}
    if scope == "access":
        return values.get("public_access_rate_requests", settings.public_access_rate_limit_requests)
    if scope == "upload":
        return values.get("public_upload_rate_limit_requests", settings.public_upload_rate_limit_requests)
    return values.get("public_rate_limit_requests", settings.public_rate_limit_requests)


def client_identity(request: Request) -> str:
    forwarded = request.headers.get("x-real-ip") or request.headers.get(
        "x-forwarded-for", ""
    ).split(",", 1)[0].strip()
    raw = forwarded or (request.client.host if request.client else "unknown")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def enforce_public_rate_limit(
    request: Request,
    app_slug: str,
    scope: str,
) -> None:
    settings = get_settings()
    values = await runtime_values()
    limit = scope_limit(scope, values)
    if limit == 0:
        return
    key = f"public-rate:{scope}:{app_slug}:{client_identity(request)}"
    client = async_redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        current, ttl = await client.eval(
            RATE_LIMIT_SCRIPT,
            1,
            key,
            values.get("public_rate_limit_window_seconds", settings.public_rate_limit_window_seconds),
        )
    except redis.RedisError as exc:
        logger.warning(
            "Unable to enforce public request rate limit",
            extra={"app_slug": app_slug, "scope": scope},
            exc_info=True,
        )
        if settings.app_env == "production":
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Public request protection is unavailable",
            ) from exc
        return
    finally:
        await client.aclose()
    if int(current) > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests",
            headers={"Retry-After": str(max(int(ttl), 1))},
        )
