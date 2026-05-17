"""Multi-instance gateway competition tests."""

from __future__ import annotations

import json
import socket
import time
import urllib.request


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _post_mcp(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def test_two_blender_servers_can_compete_for_gateway(tmp_path):
    from dcc_mcp_blender.server import BlenderMcpServer

    gateway_port = _free_port()
    s1 = BlenderMcpServer(
        port=0,
        gateway_port=gateway_port,
        registry_dir=str(tmp_path),
        enable_gateway_failover=True,
    )
    s2 = BlenderMcpServer(
        port=0,
        gateway_port=gateway_port,
        registry_dir=str(tmp_path),
        enable_gateway_failover=True,
    )

    s1.start()
    time.sleep(0.1)
    s2.start()
    time.sleep(0.1)

    try:
        assert s1.is_running
        assert s2.is_running
        assert s1.port != s2.port

        for idx, server in enumerate((s1, s2), start=1):
            response = _post_mcp(
                server.mcp_url,
                {
                    "jsonrpc": "2.0",
                    "id": idx,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest", "version": "1.0"},
                    },
                },
            )
            assert response["result"]["serverInfo"]["name"] == "dcc-mcp-blender"
    finally:
        s2.stop()
        s1.stop()
