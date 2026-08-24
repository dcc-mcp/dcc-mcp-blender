"""Typed Blender modeling entry point for auto_uv."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._modeling_ops import auto_uv


@skill_entry
def main(**kwargs) -> dict:
    """Run the bounded modeling operation."""
    return auto_uv(**kwargs)
