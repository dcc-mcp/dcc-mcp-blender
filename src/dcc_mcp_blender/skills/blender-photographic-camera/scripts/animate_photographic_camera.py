"""Animate a continuous photographic camera move."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._photographic_camera_ops import animate_photographic_camera


@skill_entry
def main(**kwargs) -> dict:
    return animate_photographic_camera(**kwargs)


if __name__ == "__main__":
    run_main(main)
