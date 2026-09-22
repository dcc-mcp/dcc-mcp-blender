"""Remove every node from the compositor tree."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._compositor_ops import clear_compositor_tree


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`clear_compositor_tree`."""
    return clear_compositor_tree(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
