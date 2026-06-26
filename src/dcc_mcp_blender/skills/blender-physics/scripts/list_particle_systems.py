"""List particle system modifiers in the Blender scene."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import list_particle_systems


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_particle_systems`."""
    return list_particle_systems(**kwargs)


if __name__ == "__main__":
    run_main(main)
