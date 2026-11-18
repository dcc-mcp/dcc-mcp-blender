"""Analyze a rendered preview still for warm saturated highlights."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._photographic_lighting_ops import analyze_photographic_test_still


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`analyze_photographic_test_still`."""
    return analyze_photographic_test_still(**kwargs)


if __name__ == "__main__":
    run_main(main)
