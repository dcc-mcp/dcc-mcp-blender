"""List rigid bodies in the current Blender scene."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import list_rigid_bodies


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_rigid_bodies`."""
    return list_rigid_bodies(**kwargs)


if __name__ == "__main__":
    run_main(main)
