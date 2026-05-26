"""Load a Blender export preset."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._interchange_ops import load_export_preset


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`load_export_preset`."""
    return load_export_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
