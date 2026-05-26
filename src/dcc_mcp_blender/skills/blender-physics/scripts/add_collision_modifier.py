"""Add a collision modifier to a mesh object."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import add_collision_modifier


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_collision_modifier`."""
    return add_collision_modifier(**kwargs)


if __name__ == "__main__":
    run_main(main)
