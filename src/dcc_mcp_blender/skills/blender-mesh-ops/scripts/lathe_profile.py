"""Typed Blender modeling entry point for lathe_profile."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._modeling_ops import lathe_profile


@skill_entry
def main(**kwargs) -> dict:
    """Run the bounded modeling operation."""
    return lathe_profile(**kwargs)
