"""Headless Blender bootstrap for the MCP server.

Run with:
    blender --background --python src/dcc_mcp_blender/blender_bootstrap.py
"""

from __future__ import annotations

from dcc_mcp_core.host import BlockingDispatcher

from dcc_mcp_blender.host import BlenderHost
from dcc_mcp_blender.server import BlenderMcpServer


def main(port: int = 18765) -> None:
    """Start the MCP server and block while Blender services dispatcher ticks."""
    dispatcher = BlockingDispatcher()
    server = BlenderMcpServer(port=port, dispatcher=dispatcher)
    server.start()
    server.discover_skills()
    print(f"MCP_URL={server.mcp_url}", flush=True)
    try:
        BlenderHost(dispatcher).run_headless()
    finally:
        server.stop()


if __name__ == "__main__":
    main()
