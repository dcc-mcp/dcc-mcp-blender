"""Validate the complete photographic toy-shot contract."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._photographic_validation_ops import validate_photographic_shot


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`validate_photographic_shot`."""
    return validate_photographic_shot(**kwargs)


if __name__ == "__main__":
    run_main(main)
