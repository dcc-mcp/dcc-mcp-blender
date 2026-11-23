"""Validate guide roots against their source mesh."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._groom_ops import validate_groom_attachment


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`validate_groom_attachment`."""
    return validate_groom_attachment(**kwargs)


if __name__ == "__main__":
    run_main(main)
