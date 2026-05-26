"""Select Blender objects by type."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_ops import select_by_type


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`select_by_type`."""
    return select_by_type(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
