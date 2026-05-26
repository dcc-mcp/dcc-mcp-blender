"""Run a named Blender development diagnostic check."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import run_check


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`run_check`."""
    return run_check(**kwargs)


if __name__ == "__main__":
    run_main(main)
