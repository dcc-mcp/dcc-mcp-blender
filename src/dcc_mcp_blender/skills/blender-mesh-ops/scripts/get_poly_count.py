"""Get polygon counts and topology statistics for a Blender mesh."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._mesh_ops import get_poly_count


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_poly_count`."""
    return get_poly_count(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
