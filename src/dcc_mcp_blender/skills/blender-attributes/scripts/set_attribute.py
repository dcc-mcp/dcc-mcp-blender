"""Set a custom property value on a Blender object."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._attributes_ops import set_attribute


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_attribute`."""
    return set_attribute(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
