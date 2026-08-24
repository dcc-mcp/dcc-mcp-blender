"""Apply and verify Blender object transforms for the modeling vocabulary."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._modeling_ops import freeze_transforms


@skill_entry
def main(**kwargs) -> dict:
    """Run the bounded modeling operation."""
    return freeze_transforms(**kwargs)
