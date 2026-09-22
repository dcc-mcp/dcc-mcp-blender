"""Update an NLA strip's timing, blending, or influence."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._nla_ops import set_nla_strip


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_nla_strip`."""
    return set_nla_strip(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
