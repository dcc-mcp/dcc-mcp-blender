"""List rigid-body constraints in the Blender scene."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import list_rigid_body_constraints


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_rigid_body_constraints`."""
    return list_rigid_body_constraints(**kwargs)


if __name__ == "__main__":
    run_main(main)
