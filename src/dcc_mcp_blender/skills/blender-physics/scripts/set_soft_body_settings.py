"""Update soft-body modifier settings on a Blender object."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._physics_ops import set_soft_body_settings


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_soft_body_settings`."""
    return set_soft_body_settings(**kwargs)


if __name__ == "__main__":
    run_main(main)
