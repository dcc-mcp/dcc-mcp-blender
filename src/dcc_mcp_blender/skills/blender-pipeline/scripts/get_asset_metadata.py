"""Get Blender asset metadata."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._asset_pipeline_ops import get_asset_metadata


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_asset_metadata`."""
    return get_asset_metadata(**kwargs)


if __name__ == "__main__":
    run_main(main)
