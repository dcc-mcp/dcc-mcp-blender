"""Run a Python script file for Blender add-on diagnostics."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import run_script


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`run_script`."""
    return run_script(**kwargs)


if __name__ == "__main__":
    run_main(main)
