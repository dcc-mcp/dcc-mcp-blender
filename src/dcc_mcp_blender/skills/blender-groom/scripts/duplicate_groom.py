"""Duplicate a generated groom for a style variant."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._groom_ops import duplicate_groom


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`duplicate_groom`."""
    return duplicate_groom(**kwargs)


if __name__ == "__main__":
    run_main(main)
