"""Enable a Blender add-on for development checks."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import enable_addon


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`enable_addon`."""
    return enable_addon(**kwargs)


if __name__ == "__main__":
    run_main(main)
