"""Get Blender simulation status."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import get_simulation_status


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_simulation_status`."""
    return get_simulation_status(**kwargs)


if __name__ == "__main__":
    run_main(main)
