"""Configure native photographic video output."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._photographic_delivery_ops import configure_photographic_video_output


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`configure_photographic_video_output`."""
    return configure_photographic_video_output(**kwargs)


if __name__ == "__main__":
    run_main(main)
