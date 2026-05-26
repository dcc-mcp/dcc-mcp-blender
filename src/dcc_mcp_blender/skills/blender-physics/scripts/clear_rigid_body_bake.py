"""Clear rigid-body simulation bakes."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import clear_rigid_body_bake


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`clear_rigid_body_bake`."""
    return clear_rigid_body_bake(**kwargs)


if __name__ == "__main__":
    run_main(main)
