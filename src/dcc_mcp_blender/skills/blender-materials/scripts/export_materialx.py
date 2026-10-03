"""Export Principled BSDF materials to a MaterialX (.mtlx) document."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._materialx_ops import export_materialx


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`export_materialx`."""
    return export_materialx(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
