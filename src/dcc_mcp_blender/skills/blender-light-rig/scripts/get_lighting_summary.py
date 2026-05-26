"""Get Blender lighting summary."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._light_rig_ops import get_lighting_summary


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_lighting_summary`."""
    return get_lighting_summary(**kwargs)


if __name__ == "__main__":
    run_main(main)
