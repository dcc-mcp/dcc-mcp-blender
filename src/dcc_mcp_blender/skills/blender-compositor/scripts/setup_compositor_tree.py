"""Enable the compositor and optionally build a starter node tree."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._compositor_ops import setup_compositor_tree


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`setup_compositor_tree`."""
    return setup_compositor_tree(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
