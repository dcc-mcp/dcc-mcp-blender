"""Bake scene rigid-body simulation caches."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import bake_rigid_body_simulation


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`bake_rigid_body_simulation`."""
    return bake_rigid_body_simulation(**kwargs)


if __name__ == "__main__":
    run_main(main)
