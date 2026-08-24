"""Typed Blender modeling entry point for create_primitive."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._modeling_ops import create_primitive


@skill_entry
def main(**kwargs) -> dict:
    """Run the bounded modeling operation."""
    return create_primitive(**kwargs)
