"""Save an image datablock back to disk."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._image_light_ops import save_image


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`save_image`."""
    return save_image(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
