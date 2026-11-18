"""Configure a physical photographic camera."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._photographic_camera_ops import configure_photographic_camera


@skill_entry
def main(**kwargs) -> dict:
    return configure_photographic_camera(**kwargs)


if __name__ == "__main__":
    run_main(main)
