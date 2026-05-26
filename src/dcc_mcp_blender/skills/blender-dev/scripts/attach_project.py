"""Attach a project checkout to Blender's Python path."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import attach_project


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`attach_project`."""
    return attach_project(**kwargs)


if __name__ == "__main__":
    run_main(main)
