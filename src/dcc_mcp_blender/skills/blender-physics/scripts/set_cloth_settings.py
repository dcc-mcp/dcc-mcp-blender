"""Update cloth modifier settings."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import set_cloth_settings


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_cloth_settings`."""
    return set_cloth_settings(**kwargs)


if __name__ == "__main__":
    run_main(main)
