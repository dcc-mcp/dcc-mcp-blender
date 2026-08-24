"""Typed Blender modeling entry point for loft_sections."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._modeling_ops import loft_sections


@skill_entry
def main(**kwargs) -> dict:
    """Run the bounded modeling operation."""
    return loft_sections(**kwargs)
