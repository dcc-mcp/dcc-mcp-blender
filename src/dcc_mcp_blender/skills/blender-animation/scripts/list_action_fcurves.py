"""List the fcurves inside an action."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._nla_ops import list_action_fcurves


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_action_fcurves`."""
    return list_action_fcurves(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
