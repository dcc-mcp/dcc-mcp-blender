"""Create a Blender HDRI world."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._light_rig_ops import create_hdri_world


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`create_hdri_world`."""
    return create_hdri_world(**kwargs)


if __name__ == "__main__":
    run_main(main)
