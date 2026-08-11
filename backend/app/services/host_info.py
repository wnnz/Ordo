from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings


def execute_host_info_node(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    settings = get_settings()
    token = settings.host_info_agent_token or settings.sandbox_shared_secret
    if not token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Host information agent token is not configured"
        )
    timeout = float(config.get("timeout_seconds", 10))
    try:
        response = httpx.get(
            f"{settings.host_info_agent_url.rstrip('/')}/v1/host-info",
            headers={"X-Ordo-Host-Token": token},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Host information agent unavailable: {exc}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("primary_ipv4"), str):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Host information agent returned invalid data")
    return payload
