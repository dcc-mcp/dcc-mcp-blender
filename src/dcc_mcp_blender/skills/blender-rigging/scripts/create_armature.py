"""Create a Blender armature."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._rigging_ops import create_armature


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`create_armature`."""
    return create_armature(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
