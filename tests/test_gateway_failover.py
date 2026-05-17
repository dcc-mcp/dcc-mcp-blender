"""Gateway failover smoke tests."""

from __future__ import annotations

import socket
import time


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_non_gateway_instance_survives_gateway_shutdown(tmp_path):
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
        s1.stop()
        time.sleep(0.2)
        assert s2.is_running
        assert s2.port > 0
    finally:
        s2.stop()
