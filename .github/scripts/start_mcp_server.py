"""Start a Blender-backed MCP server for CI connectivity checks."""

from __future__ import annotations

import os
import sys
import time

try:
    import bpy  # noqa: F401
except ImportError:
    print("WARNING: bpy not available, skipping MCP server test")
    sys.exit(0)

import dcc_mcp_blender
from dcc_mcp_blender.host import BlenderCallableDispatcher, BlenderHost


def main() -> None:
    dispatcher = BlenderCallableDispatcher()
    host = BlenderHost(dispatcher)
    server = dcc_mcp_blender.start_server(port=8765, dispatcher=dispatcher)
    host.start()
    print(f"MCP server started at {server.mcp_url}", flush=True)

    for skill in server.list_skills():
        name = skill.get("name", "")
        if name and not server.is_skill_loaded(name):
            try:
                server.load_skill(name)
            except Exception as exc:
                print(f"WARNING: failed to load skill {name}: {exc}", flush=True)

    print(f"Loaded skills: {server.loaded_skill_count()}", flush=True)
    print(f"All skills: {[s.get('name', '?') for s in server.list_skills()]}", flush=True)

    sentinel = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "mcp_test_done")
    try:
        while not os.path.exists(sentinel):
            time.sleep(1)
    finally:
        host.stop()
        dcc_mcp_blender.stop_server()
        print("MCP server stopped.", flush=True)


if __name__ == "__main__":
    main()
