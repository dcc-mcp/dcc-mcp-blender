"""Capture structured Blender UI metadata."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import capture_ui_snapshot


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`capture_ui_snapshot`."""
    return capture_ui_snapshot(**kwargs)


if __name__ == "__main__":
    run_main(main)
