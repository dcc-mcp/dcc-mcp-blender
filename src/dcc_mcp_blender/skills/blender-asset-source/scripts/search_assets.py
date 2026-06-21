"""Search for discoverable assets and return validated AssetDescriptor[]."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._asset_source_ops import search_assets as _search_assets


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`_asset_source_ops.search_assets`."""
    return _search_assets(**kwargs)


if __name__ == "__main__":
    run_main(main)
