"""Bake Blender lighting."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._material_pipeline_ops import bake_lighting


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`bake_lighting`."""
    return bake_lighting(**kwargs)


if __name__ == "__main__":
    run_main(main)
