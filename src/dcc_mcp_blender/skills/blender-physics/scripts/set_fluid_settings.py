"""Update Mantaflow fluid settings."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._physics_ops import set_fluid_settings


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_fluid_settings`."""
    return set_fluid_settings(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
