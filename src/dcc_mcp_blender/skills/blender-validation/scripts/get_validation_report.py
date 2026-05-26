"""Return stored Blender validation reports."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._asset_pipeline_ops import get_validation_report


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_validation_report`."""
    return get_validation_report(**kwargs)


if __name__ == "__main__":
    run_main(main)
