"""Extrude a bounded face selection through Blender's mesh operator."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._modeling_ops import extrude_faces


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`extrude_faces`."""
    return extrude_faces(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
