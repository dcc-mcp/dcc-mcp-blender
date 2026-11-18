"""Render one temporary photographic preview still."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._render_profile_ops import render_photographic_test_still


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`render_photographic_test_still`."""
    return render_photographic_test_still(**kwargs)


if __name__ == "__main__":
    run_main(main)
