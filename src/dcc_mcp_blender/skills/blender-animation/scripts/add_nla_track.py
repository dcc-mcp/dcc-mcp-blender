"""Create an NLA track on an object."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._nla_ops import add_nla_track


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_nla_track`."""
    return add_nla_track(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
