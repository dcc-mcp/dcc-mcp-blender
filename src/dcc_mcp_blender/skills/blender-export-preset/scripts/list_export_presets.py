"""List Blender export presets."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._interchange_ops import list_export_presets


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_export_presets`."""
    return list_export_presets(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
