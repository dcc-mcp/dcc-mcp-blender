"""List NLA tracks and their strips on an object."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._nla_ops import list_nla_tracks


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_nla_tracks`."""
    return list_nla_tracks(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
