"""Attach an IES photometric profile to a light."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._image_light_ops import set_light_ies


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_light_ies`."""
    return set_light_ies(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
