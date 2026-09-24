"""Headless Blender bootstrap for the MCP server.

Run with:
    blender --background --python src/dcc_mcp_blender/blender_bootstrap.py

Blender 5.x boots an isolated interpreter that ignores ``PYTHONPATH``, so on
those hosts this script is reachable (Blender loads it by path) while the
package it belongs to is not importable yet. The path helper is therefore
loaded by file path and run before any adapter import.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Optional

_HELPER_NAME = "_dcc_mcp_blender_path_repair"


def _load_path_helper():
    """Load the dependency-free path helper from the package directory."""
    cached = sys.modules.get(_HELPER_NAME)
    if cached is not None:
        return cached
    helper = Path(__file__).resolve().with_name("_isolated_path.py")
    spec = importlib.util.spec_from_file_location(_HELPER_NAME, helper)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_HELPER_NAME] = module
    spec.loader.exec_module(module)
    return module


_repaired = []
_helper = _load_path_helper()
if _helper is not None:
    _repaired = _helper.repair_sys_path()
    if _repaired:
        print(
            f"[dcc-mcp-blender] restored {len(_repaired)} PYTHONPATH entr(ies) that isolated "
            "Blender Python had dropped",
            flush=True,
        )

from dcc_mcp_core.host import BlockingDispatcher  # noqa: E402

from dcc_mcp_blender.host import BlenderHost  # noqa: E402
from dcc_mcp_blender.server import BlenderMcpServer  # noqa: E402


def main(port: Optional[int] = None) -> None:
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
