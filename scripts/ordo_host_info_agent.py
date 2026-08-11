from __future__ import annotations

import argparse
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


POWERSHELL = r"""
$items = Get-NetIPConfiguration | Where-Object {
  $_.IPv4Address -and $_.NetAdapter.Status -eq 'Up'
} | ForEach-Object {
  [PSCustomObject]@{
    name = $_.InterfaceAlias
    ipv4 = @($_.IPv4Address | ForEach-Object { $_.IPAddress })
    gateway = @($_.IPv4DefaultGateway | ForEach-Object { $_.NextHop })
    dns = @($_.DNSServer.ServerAddresses)
    metric = $_.NetIPInterface.InterfaceMetric
  }
}
$items | ConvertTo-Json -Compress -Depth 5
"""


def collect_host_info() -> dict:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    raw = json.loads(completed.stdout or "[]")
    adapters = raw if isinstance(raw, list) else [raw]
    adapters = [item for item in adapters if isinstance(item, dict)]
    candidates = [
        item
        for item in adapters
        if any(str(gateway).strip() and gateway is not None for gateway in item.get("gateway", []))
        and any(
            not str(address).startswith(("127.", "169.254."))
            for address in item.get("ipv4", [])
        )
    ]
    primary = min(candidates, key=lambda item: int(item.get("metric") or 2**31), default={})
    primary_ipv4 = next(
        (
            str(address)
            for address in primary.get("ipv4", [])
            if not str(address).startswith(("127.", "169.254."))
        ),
        "",
    )
    return {
        "source": "windows-host-agent",
        "primary_ipv4": primary_ipv4,
        "primary_interface": str(primary.get("name") or ""),
        "adapters": adapters,
    }


class Handler(BaseHTTPRequestHandler):
    token = ""

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
            return
        if self.path != "/v1/host-info":
            self.send_json(404, {"error": "not_found"})
            return
        if not self.token or self.headers.get("X-Ordo-Host-Token", "") != self.token:
            self.send_json(401, {"error": "unauthorized"})
            return
        try:
            self.send_json(200, collect_host_info())
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self.send_json(500, {"error": "collection_failed", "detail": str(exc)[:500]})

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ordo read-only Windows host information agent")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    Handler.token = os.environ.get("ORDO_HOST_INFO_TOKEN", "")
    if not Handler.token:
        raise SystemExit("ORDO_HOST_INFO_TOKEN is required")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Ordo host info agent listening on {args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
