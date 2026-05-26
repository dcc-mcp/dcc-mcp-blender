"""List Blender simulation modifiers."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import list_simulation_modifiers


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_simulation_modifiers`."""
    return list_simulation_modifiers(**kwargs)


if __name__ == "__main__":
    run_main(main)
