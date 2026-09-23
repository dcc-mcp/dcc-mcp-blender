"""List the UDIM tiles of an image."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._image_light_ops import list_image_tiles


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_image_tiles`."""
    return list_image_tiles(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
