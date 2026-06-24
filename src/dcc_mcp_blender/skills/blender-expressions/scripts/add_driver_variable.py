"""Add a variable to an existing Blender driver."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._expressions_ops import add_driver_variable


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_driver_variable`."""
    return add_driver_variable(**kwargs)


if __name__ == "__main__":
    run_main(main)
