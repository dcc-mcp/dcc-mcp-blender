"""Set a material attribute or shader input."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._material_pipeline_ops import set_material_attribute


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_material_attribute`."""
    return set_material_attribute(**kwargs)


if __name__ == "__main__":
    run_main(main)
