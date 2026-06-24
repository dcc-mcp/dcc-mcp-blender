"""Update the expression of an existing Blender driver."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._expressions_ops import set_driver_expression


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_driver_expression`."""
    return set_driver_expression(**kwargs)


if __name__ == "__main__":
    run_main(main)
