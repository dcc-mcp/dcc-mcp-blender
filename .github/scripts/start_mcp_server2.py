"""Start a second Blender-backed MCP server on a random port for CI."""

from __future__ import annotations

import os
import sys
import threading
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
    print(f"Second instance MCP URL: {server.mcp_url}", flush=True)

    url_path = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "mcp_server2_url")
    with open(url_path, "w", encoding="utf-8") as handle:
        handle.write(server.mcp_url)

    sentinel = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "mcp_test2_done")
    stop_event = threading.Event()

    def _watch_sentinel() -> None:
        while not os.path.exists(sentinel):
            time.sleep(1)
        stop_event.set()

    threading.Thread(target=_watch_sentinel, name="mcp-sentinel-2", daemon=True).start()
    try:
        host.run_headless(stop_event=stop_event)
    finally:
        dcc_mcp_blender.stop_server()
        host.stop()


if __name__ == "__main__":
    main()
