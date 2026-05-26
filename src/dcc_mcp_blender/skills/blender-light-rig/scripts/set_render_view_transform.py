"""Set Blender render view transform controls."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._light_rig_ops import set_render_view_transform


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_render_view_transform`."""
    return set_render_view_transform(**kwargs)


if __name__ == "__main__":
    run_main(main)
