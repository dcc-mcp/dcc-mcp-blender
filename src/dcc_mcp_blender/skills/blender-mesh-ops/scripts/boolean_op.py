"""Typed Blender modeling entry point for boolean_op."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._modeling_ops import boolean_op


@skill_entry
def main(**kwargs) -> dict:
    """Run the bounded modeling operation."""
    return boolean_op(**kwargs)
