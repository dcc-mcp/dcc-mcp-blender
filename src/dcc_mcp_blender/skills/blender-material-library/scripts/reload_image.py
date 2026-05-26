"""Reload a Blender image."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._material_pipeline_ops import reload_image


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`reload_image`."""
    return reload_image(**kwargs)


if __name__ == "__main__":
    run_main(main)
