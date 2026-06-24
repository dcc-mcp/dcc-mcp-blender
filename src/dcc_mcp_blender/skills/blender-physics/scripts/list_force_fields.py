"""List objects with an active force field in the Blender scene."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import list_force_fields


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_force_fields`."""
    return list_force_fields(**kwargs)


if __name__ == "__main__":
    run_main(main)
