"""Add a force-field physics property to a Blender object."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import add_force_field


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_force_field`."""
    return add_force_field(**kwargs)


if __name__ == "__main__":
    run_main(main)
