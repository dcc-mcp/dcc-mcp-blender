"""Create a three-point Blender light rig."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._light_rig_ops import create_three_point_light_rig


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`create_three_point_light_rig`."""
    return create_three_point_light_rig(**kwargs)


if __name__ == "__main__":
    run_main(main)
