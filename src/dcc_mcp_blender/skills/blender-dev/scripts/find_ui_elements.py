"""Find structured Blender UI metadata entries."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import find_ui_elements


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`find_ui_elements`."""
    return find_ui_elements(**kwargs)


if __name__ == "__main__":
    run_main(main)
