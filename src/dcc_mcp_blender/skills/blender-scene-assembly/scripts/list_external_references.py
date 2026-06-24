"""List all external .blend file references (library linking)."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_assembly_ops import list_external_references


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_external_references`."""
    return list_external_references(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
