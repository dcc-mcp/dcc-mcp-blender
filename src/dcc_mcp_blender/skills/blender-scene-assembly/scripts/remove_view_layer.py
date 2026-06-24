"""Remove a view layer from a scene."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_assembly_ops import remove_view_layer


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`remove_view_layer`."""
    return remove_view_layer(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
