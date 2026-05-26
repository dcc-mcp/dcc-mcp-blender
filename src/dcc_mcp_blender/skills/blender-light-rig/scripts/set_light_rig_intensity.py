"""Set Blender light rig intensity."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._light_rig_ops import set_light_rig_intensity


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_light_rig_intensity`."""
    return set_light_rig_intensity(**kwargs)


if __name__ == "__main__":
    run_main(main)
