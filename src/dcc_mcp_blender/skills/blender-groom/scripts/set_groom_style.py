"""Update a generated groom's width, length, or material style."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._groom_ops import set_groom_style


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_groom_style`."""
    return set_groom_style(**kwargs)


if __name__ == "__main__":
    run_main(main)
