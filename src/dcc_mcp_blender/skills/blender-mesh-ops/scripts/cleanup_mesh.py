"""Clean up Blender mesh topology."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._mesh_ops import cleanup_mesh


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`cleanup_mesh`."""
    return cleanup_mesh(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
