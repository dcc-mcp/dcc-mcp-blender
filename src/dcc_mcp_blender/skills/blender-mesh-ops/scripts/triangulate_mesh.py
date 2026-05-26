"""Triangulate Blender mesh faces."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._mesh_ops import triangulate_mesh


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`triangulate_mesh`."""
    return triangulate_mesh(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
