"""List drivers on a Blender object or across the whole scene."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._expressions_ops import list_drivers


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_drivers`."""
    return list_drivers(**kwargs)


if __name__ == "__main__":
    run_main(main)
