"""Configure child particles on a particle system."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._physics_ops import set_particle_children


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_particle_children`."""
    return set_particle_children(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
