"""Reload Python modules during Blender add-on development."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import reload_modules


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`reload_modules`."""
    return reload_modules(**kwargs)


if __name__ == "__main__":
    run_main(main)
