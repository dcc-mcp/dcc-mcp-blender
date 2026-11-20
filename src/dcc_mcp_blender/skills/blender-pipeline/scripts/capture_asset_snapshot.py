"""Capture a deterministic Blender scene snapshot."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._asset_build_ops import capture_asset_snapshot


@skill_entry
def main(**kwargs) -> dict:
    return capture_asset_snapshot(**kwargs)


if __name__ == "__main__":
    run_main(main)
