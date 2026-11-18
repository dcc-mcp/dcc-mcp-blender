"""Contract tests for photographic post and delivery skills."""

from __future__ import annotations

from pathlib import Path

import yaml

from dcc_mcp_blender._photographic_delivery_ops import (
    VIDEO_COLOR_SPACE,
    VIDEO_CRF,
    VIDEO_FPS,
    VIDEO_PIXEL_FORMAT,
    _sequence_pattern,
    encode_photographic_video,
)
from dcc_mcp_blender._photographic_post_ops import (
    DEFAULT_HALATION_THRESHOLD,
    _grain_pixels,
    configure_photographic_post,
)
from dcc_mcp_blender._photographic_validation_ops import validate_photographic_shot


def test_photographic_post_defaults_and_grain_are_frame_deterministic():
    assert DEFAULT_HALATION_THRESHOLD == 185.0 / 255.0
    assert _grain_pixels(2, 1337, 1) == _grain_pixels(2, 1337, 1)
    assert _grain_pixels(2, 1337, 1) != _grain_pixels(2, 1337, 2)


def test_photographic_post_rejects_invalid_grain_size_without_blender():
    result = configure_photographic_post(grain_size=8)

    assert result["success"] is False
    assert "grain_size" in result["error"]


def test_delivery_contract_and_sequence_pattern():
    assert (VIDEO_FPS, VIDEO_CRF, VIDEO_PIXEL_FORMAT, VIDEO_COLOR_SPACE) == (24, 15, "yuv420p", "bt709")
    assert _sequence_pattern("C:/renders/toy_####.jpg") == "C:/renders/toy_%04d.jpg"
    assert _sequence_pattern("C:/renders/toy_%04d.jpg") == "C:/renders/toy_%04d.jpg"


def test_delivery_rejects_reversed_frame_range():
    result = encode_photographic_video("frames_####.jpg", "movie.mp4", 10, 1)

    assert result["success"] is False
    assert "end_frame" in result["error"]


def test_tools_yaml_declares_photographic_contracts():
    root = Path("src/dcc_mcp_blender/skills")
    post = yaml.safe_load((root / "blender-photographic-post/tools.yaml").read_text(encoding="utf-8"))
    delivery = yaml.safe_load((root / "blender-photographic-delivery/tools.yaml").read_text(encoding="utf-8"))
    validation = yaml.safe_load((root / "blender-validation/tools.yaml").read_text(encoding="utf-8"))
    render_profile = yaml.safe_load((root / "blender-render-profile/tools.yaml").read_text(encoding="utf-8"))

    assert {tool["name"] for tool in post["tools"]} == {
        "configure_photographic_post",
        "validate_photographic_post",
    }
    assert {tool["name"] for tool in delivery["tools"]} == {
        "configure_photographic_video_output",
        "validate_photographic_video_output",
        "encode_photographic_video",
    }
    photographic_validation = next(
        tool for tool in validation["tools"] if tool["name"] == "validate_photographic_shot"
    )
    assert set(photographic_validation["input_schema"]["required"]) == {
        "hero_object",
        "focus_object",
        "background_object",
        "floor_object",
        "wall_object",
        "source_name",
    }
    assert "render_photographic_test_still" in {tool["name"] for tool in render_profile["tools"]}


def test_photographic_shot_request_validates_before_blender_import():
    result = validate_photographic_shot(shot_type="unsupported")

    assert result["success"] is False
    assert "shot_type" in result["error"]
