"""Gateway configuration tests for BlenderMcpServer."""

from __future__ import annotations

import socket


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_gateway_params_start_server_with_failover_enabled(tmp_path):
    from dcc_mcp_blender.server import BlenderMcpServer

    gateway_port = _free_port()
    server = BlenderMcpServer(
        port=0,
        gateway_port=gateway_port,
        registry_dir=str(tmp_path),
        enable_gateway_failover=True,
        dcc_version="4.2.0",
        scene="/tmp/scene.blend",
    )
    server.start()
    try:
        assert server.is_running
        assert server.port > 0
        assert server.get_gateway_election_status() is not None
    finally:
        server.stop()
