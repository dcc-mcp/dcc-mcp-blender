"""Report where an image lives and whether its file is reachable."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._image_light_ops import image_file_status


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`image_file_status`."""
    return image_file_status(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
