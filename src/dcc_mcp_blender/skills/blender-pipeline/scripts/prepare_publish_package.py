"""Prepare a local Blender publish package."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._asset_pipeline_ops import prepare_publish_package


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`prepare_publish_package`."""
    return prepare_publish_package(**kwargs)


if __name__ == "__main__":
    run_main(main)
