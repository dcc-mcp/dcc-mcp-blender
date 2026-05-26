"""Delete a Blender material preset."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._material_pipeline_ops import delete_material_preset


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`delete_material_preset`."""
    return delete_material_preset(**kwargs)


if __name__ == "__main__":
    run_main(main)
