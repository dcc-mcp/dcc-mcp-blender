"""List UV maps on a Blender mesh object."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._uv_ops import list_uv_maps


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_uv_maps`."""
    return list_uv_maps(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
