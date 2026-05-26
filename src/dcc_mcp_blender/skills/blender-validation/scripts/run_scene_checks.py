"""Run Blender scene validation checks."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._asset_pipeline_ops import run_scene_checks


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`run_scene_checks`."""
    return run_scene_checks(**kwargs)


if __name__ == "__main__":
    run_main(main)
