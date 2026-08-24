"""Typed Blender modeling entry point for delete_history."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._modeling_ops import delete_history


@skill_entry
def main(**kwargs) -> dict:
    """Run the bounded modeling operation."""
    return delete_history(**kwargs)
