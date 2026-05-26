"""List Blender material presets."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._material_pipeline_ops import list_material_presets


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_material_presets`."""
    return list_material_presets(**kwargs)


if __name__ == "__main__":
    run_main(main)
