"""Inspect generated groom guide curves."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._groom_ops import inspect_grooms


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`inspect_grooms`."""
    return inspect_grooms(**kwargs)


if __name__ == "__main__":
    run_main(main)
