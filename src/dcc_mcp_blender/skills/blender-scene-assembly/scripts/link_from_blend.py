"""Link data blocks from an external .blend file (library reference)."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_assembly_ops import link_from_blend


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`link_from_blend`."""
    return link_from_blend(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
