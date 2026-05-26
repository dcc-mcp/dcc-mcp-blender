"""Delete Blender keyframes for an object."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._animation_ops import delete_keyframes


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`delete_keyframes`."""
    return delete_keyframes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
