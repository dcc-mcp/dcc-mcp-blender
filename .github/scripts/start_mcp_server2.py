"""Start a second Blender-backed MCP server on a random port for CI."""

from __future__ import annotations

import os
import sys
import time

try:
    import bpy  # noqa: F401
except ImportError:
    sys.exit(0)

import dcc_mcp_blender
from dcc_mcp_blender.host import BlenderCallableDispatcher, BlenderHost


def main() -> None:
    dispatcher = BlenderCallableDispatcher()
    host = BlenderHost(dispatcher)
    server = dcc_mcp_blender.start_server(port=0, dispatcher=dispatcher)
    host.start()
    print(f"Second instance MCP URL: {server.mcp_url}", flush=True)

    url_path = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "mcp_server2_url")
    with open(url_path, "w", encoding="utf-8") as handle:
        handle.write(server.mcp_url)

    sentinel = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "mcp_test2_done")
    try:
        while not os.path.exists(sentinel):
            time.sleep(1)
    finally:
        host.stop()
        dcc_mcp_blender.stop_server()


if __name__ == "__main__":
    main()
