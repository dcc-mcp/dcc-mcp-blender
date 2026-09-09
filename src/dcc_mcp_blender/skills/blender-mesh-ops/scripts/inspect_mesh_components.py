"""Inspect a bounded page of original Blender mesh components."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._mesh_query_ops import inspect_mesh_components


@skill_entry
def main(**kwargs) -> dict:
    """Run the typed component query."""
    return inspect_mesh_components(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
