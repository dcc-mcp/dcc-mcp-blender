"""Disable and uninstall a Blender add-on."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._dev_ops import remove_addon


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`remove_addon`."""
    return remove_addon(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
