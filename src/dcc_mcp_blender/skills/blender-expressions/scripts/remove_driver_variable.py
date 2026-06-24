"""Remove a named variable from an existing Blender driver."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._expressions_ops import remove_driver_variable


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`remove_driver_variable`."""
    return remove_driver_variable(**kwargs)


if __name__ == "__main__":
    run_main(main)
