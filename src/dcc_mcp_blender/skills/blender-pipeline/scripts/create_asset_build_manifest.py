"""Create a scene-stored asset build manifest."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._asset_build_ops import create_asset_build_manifest


@skill_entry
def main(**kwargs) -> dict:
    return create_asset_build_manifest(**kwargs)


if __name__ == "__main__":
    run_main(main)
