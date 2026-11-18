"""Encode a photographic frame sequence with FFmpeg."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._photographic_delivery_ops import encode_photographic_video


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`encode_photographic_video`."""
    return encode_photographic_video(**kwargs)


if __name__ == "__main__":
    run_main(main)
