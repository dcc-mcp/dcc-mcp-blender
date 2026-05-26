"""Create or update a Blender driver."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._rigging_ops import set_driver


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_driver`."""
    return set_driver(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
