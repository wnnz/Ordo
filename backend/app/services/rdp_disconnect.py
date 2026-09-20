from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings


def execute_rdp_disconnect_node(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    settings = get_settings()
    token = settings.host_info_agent_token or settings.sandbox_shared_secret
    if not token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Windows agent token is not configured"
        )

    request_body: dict[str, int] = {}
    raw_session_id = config.get("session_id")
    if raw_session_id not in (None, ""):
        try:
            session_id = int(raw_session_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "RDP session id must be an integer"
            ) from exc
        if session_id < 1:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "RDP session id must be positive"
            )
        request_body["session_id"] = session_id

    timeout = float(config.get("timeout_seconds", 10))
    try:
        response = httpx.post(
            f"{settings.host_info_agent_url.rstrip('/')}/v1/rdp/disconnect",
            headers={"X-Ordo-Host-Token": token},
            json=request_body,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Windows agent unavailable: {exc}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("disconnected_count"), int)
        or not isinstance(payload.get("sessions"), list)
        or not isinstance(payload.get("ok"), bool)
    ):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Windows agent returned invalid data")
    return payload
