"""Clear Blender simulation modifier caches."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import clear_simulation_cache


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`clear_simulation_cache`."""
    return clear_simulation_cache(**kwargs)


if __name__ == "__main__":
    run_main(main)
