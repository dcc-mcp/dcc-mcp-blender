"""Comb and shape generated groom guide curves."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._groom_ops import shape_groom_guides


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`shape_groom_guides`."""
    return shape_groom_guides(**kwargs)


if __name__ == "__main__":
    run_main(main)
