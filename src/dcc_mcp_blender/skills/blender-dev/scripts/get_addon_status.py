"""Get structured Blender add-on status."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import get_addon_status


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_addon_status`."""
    return get_addon_status(**kwargs)


if __name__ == "__main__":
    run_main(main)
