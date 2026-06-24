"""Remove a force-field physics property from a Blender object."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import remove_force_field


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`remove_force_field`."""
    return remove_force_field(**kwargs)


if __name__ == "__main__":
    run_main(main)
