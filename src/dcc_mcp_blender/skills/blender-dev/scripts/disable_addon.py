"""Disable a Blender add-on for development checks."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import disable_addon


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`disable_addon`."""
    return disable_addon(**kwargs)


if __name__ == "__main__":
    run_main(main)
