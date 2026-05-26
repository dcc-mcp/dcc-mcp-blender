"""Freeze Blender object transforms."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_ops import freeze_transforms


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`freeze_transforms`."""
    return freeze_transforms(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
