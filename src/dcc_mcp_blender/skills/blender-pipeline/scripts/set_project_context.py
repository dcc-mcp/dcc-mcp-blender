"""Set Blender project context metadata."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._asset_pipeline_ops import set_project_context


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_project_context`."""
    return set_project_context(**kwargs)


if __name__ == "__main__":
    run_main(main)
