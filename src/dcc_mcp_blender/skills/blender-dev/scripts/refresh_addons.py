"""Rescan add-on paths so newly installed add-ons appear."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._dev_ops import refresh_addons


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`refresh_addons`."""
    return refresh_addons(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
