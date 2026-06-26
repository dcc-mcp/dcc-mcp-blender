"""Add a particle system modifier to a Blender mesh object."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import add_particle_system


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_particle_system`."""
    return add_particle_system(**kwargs)


if __name__ == "__main__":
    run_main(main)
