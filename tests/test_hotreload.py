"""Hot-reload integration tests for BlenderMcpServer."""

from __future__ import annotations


def test_hot_reload_enable_disable_round_trip():
    from dcc_mcp_blender.server import BlenderMcpServer

    server = BlenderMcpServer(port=0)
    try:
        assert server.is_hot_reload_enabled is False
        server.enable_hot_reload()
        assert server.is_hot_reload_enabled is True
        stats = server.hot_reload_stats
        assert isinstance(stats, dict)
        server.disable_hot_reload()
        assert server.is_hot_reload_enabled is False
    finally:
        server.stop()
