"""Apply a photographic Cycles render profile."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._render_profile_ops import apply_render_profile


@skill_entry
def main(**kwargs) -> dict:
    return apply_render_profile(**kwargs)


if __name__ == "__main__":
    run_main(main)
