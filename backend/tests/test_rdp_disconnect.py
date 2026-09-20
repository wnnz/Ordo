from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

import app.services.rdp_disconnect as rdp_disconnect


def test_rdp_disconnect_node_calls_protected_windows_agent(monkeypatch):
    settings = SimpleNamespace(
        host_info_agent_url="http://host.docker.internal:8765/",
        host_info_agent_token="dedicated-token",
        sandbox_shared_secret="fallback-token",
    )
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "ok": True,
                "disconnected_count": 1,
                "sessions": [{"session_id": 7}],
                "failed": [],
                "message": "done",
            }

    def post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(rdp_disconnect, "get_settings", lambda: settings)
    monkeypatch.setattr(rdp_disconnect.httpx, "post", post)

    result = rdp_disconnect.execute_rdp_disconnect_node(
        {"session_id": "7", "timeout_seconds": 4}, {}
    )

    assert result["disconnected_count"] == 1
    assert captured == {
        "url": "http://host.docker.internal:8765/v1/rdp/disconnect",
        "headers": {"X-Ordo-Host-Token": "dedicated-token"},
        "json": {"session_id": 7},
        "timeout": 4.0,
    }


def test_rdp_disconnect_node_rejects_bad_input_and_agent_payload(monkeypatch):
    settings = SimpleNamespace(
        host_info_agent_url="http://agent",
        host_info_agent_token="token",
        sandbox_shared_secret="",
    )
    monkeypatch.setattr(rdp_disconnect, "get_settings", lambda: settings)

    with pytest.raises(HTTPException, match="must be an integer"):
        rdp_disconnect.execute_rdp_disconnect_node({"session_id": "not-a-number"}, {})

    response = httpx.Response(
        200,
        json={"ok": True, "disconnected_count": "1", "sessions": []},
        request=httpx.Request("POST", "http://agent/v1/rdp/disconnect"),
    )
    monkeypatch.setattr(rdp_disconnect.httpx, "post", lambda *args, **kwargs: response)
    with pytest.raises(HTTPException, match="invalid data"):
        rdp_disconnect.execute_rdp_disconnect_node({}, {})
