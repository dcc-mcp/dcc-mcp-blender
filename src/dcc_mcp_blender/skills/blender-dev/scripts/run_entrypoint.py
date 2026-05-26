"""Run a Python module entrypoint for Blender add-on diagnostics."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import run_entrypoint


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`run_entrypoint`."""
    return run_entrypoint(**kwargs)


if __name__ == "__main__":
    run_main(main)
