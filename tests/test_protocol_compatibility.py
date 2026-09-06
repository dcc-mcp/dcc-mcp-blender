"""Adapter-facing MCP protocol compatibility checks.

These tests intentionally exercise the HTTP boundary through the public
``BlenderMcpServer`` rather than importing dcc-mcp-core implementation
details. The matrix is the contract this adapter ships against:

* 2025-03-26 remains supported for legacy MCP clients;
* 2025-06-18 is the current session-based default;
* newer/unknown protocol versions fail closed to Core's session default.

The 2026 stateless protocol is tracked in ``docs/protocol-compatibility.md``
but is not claimed by this adapter until a released Core wheel enables it.
"""

from __future__ import annotations

import json
import urllib.request

import pytest


@pytest.fixture()
def running_server():
    """Start an isolated adapter HTTP server for one compatibility check."""
    from dcc_mcp_blender.server import BlenderMcpServer

    server = BlenderMcpServer(port=0, gateway_port=0, enable_gateway_failover=False)
    server.start()
    try:
        yield server
    finally:
        server.stop()


def _initialize(server, requested_version=None):
    params = {
        "capabilities": {},
        "clientInfo": {"name": "dcc-mcp-blender-contract-test", "version": "1"},
    }
    if requested_version is not None:
        params["protocolVersion"] = requested_version
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params}).encode("utf-8")
    request = urllib.request.Request(
        server.mcp_url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


@pytest.mark.parametrize(
    ("requested_version", "negotiated_version"),
    (
        ("2025-03-26", "2025-03-26"),
        ("2025-06-18", "2025-06-18"),
        ("2026-07-28", "2025-06-18"),
        ("2099-01-01", "2025-06-18"),
        (None, "2025-06-18"),
    ),
)
def test_initialize_protocol_matrix(running_server, requested_version, negotiated_version):
    """The adapter preserves legacy negotiation and Core's default fallback."""
    response = _initialize(running_server, requested_version)

    assert response["jsonrpc"] == "2.0"
    assert response["result"]["protocolVersion"] == negotiated_version


def test_initialize_identity_is_adapter_owned(running_server):
    """Core owns the envelope; Blender owns the server identity fields."""
    result = _initialize(running_server, "2025-06-18")["result"]

    from dcc_mcp_blender.server import SERVER_NAME, SERVER_VERSION

    assert result["serverInfo"] == {"name": SERVER_NAME, "version": SERVER_VERSION}
