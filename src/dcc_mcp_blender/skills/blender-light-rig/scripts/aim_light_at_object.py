"""Aim a Blender light at an object."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._light_rig_ops import aim_light_at_object


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`aim_light_at_object`."""
    return aim_light_at_object(**kwargs)


if __name__ == "__main__":
    run_main(main)
