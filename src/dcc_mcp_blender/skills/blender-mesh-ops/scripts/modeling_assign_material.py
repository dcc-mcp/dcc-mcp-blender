"""Assign and verify a Blender material for the modeling vocabulary."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._modeling_ops import assign_material


@skill_entry
def main(**kwargs) -> dict:
    """Run the bounded modeling operation."""
    return assign_material(**kwargs)
