"""Get material node connections."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._material_pipeline_ops import get_material_connections


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_material_connections`."""
    return get_material_connections(**kwargs)


if __name__ == "__main__":
    run_main(main)
