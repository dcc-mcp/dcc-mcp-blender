"""Set properties on a Blender object constraint."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._rigging_ops import set_constraint_properties


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_constraint_properties`."""
    return set_constraint_properties(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
