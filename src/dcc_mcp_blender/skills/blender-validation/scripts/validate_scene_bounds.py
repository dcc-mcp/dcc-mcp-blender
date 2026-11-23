"""Validate a selected Blender scene projection and its bounds."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._asset_pipeline_ops import validate_scene_bounds


@skill_entry
def main(**kwargs) -> dict:
    return validate_scene_bounds(**kwargs)


if __name__ == "__main__":
    run_main(main)
