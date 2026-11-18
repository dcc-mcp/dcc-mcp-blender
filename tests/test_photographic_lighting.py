"""Tests for the motivated photographic lighting contract."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from dcc_mcp_blender._photographic_color_ops import analyze_rgb_pixels
from dcc_mcp_blender._photographic_lighting_ops import configure_motivated_lighting
from tests.conftest import load_and_call


def test_outdoor_lighting_requires_an_hdri_path():
    result = configure_motivated_lighting(source_name="Outdoor", source_type="OUTDOOR_HDRI")

    assert result["success"] is False
    assert "hdri_path" in result["error"]


def test_tools_yaml_declares_motivated_lighting_contract():
    path = Path("src/dcc_mcp_blender/skills/blender-photographic-lighting/tools.yaml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in document["tools"]}

    assert set(tools) == {
        "configure_motivated_lighting",
        "validate_motivated_lighting",
        "analyze_photographic_test_still",
    }
    assert "OUTDOOR_HDRI" in tools["configure_motivated_lighting"]["input_schema"]["properties"]["source_type"]["enum"]
    assert tools["validate_motivated_lighting"]["read_only"] is True


def test_color_analysis_detects_warm_saturated_highlights_without_mutating_materials():
    result = analyze_rgb_pixels(
        [
            0.95,
            0.38,
            0.18,
            1.0,
            0.90,
            0.88,
            0.87,
            1.0,
            0.2,
            0.25,
            0.3,
            1.0,
        ],
        highlight_threshold=0.7,
        warning_ratio=0.5,
    )

    assert result["highlight_pixel_count"] == 2
    assert result["saturated_highlight_count"] == 1
    assert result["warm_highlight_ratio"] == 1.0
    assert result["recommend_lower_key_energy"] is True
    assert result["material_color_mutated"] is False


def test_color_analysis_does_not_flag_neutral_highlights():
    result = analyze_rgb_pixels([0.9, 0.89, 0.88, 1.0], highlight_threshold=0.7)

    assert result["highlight_pixel_count"] == 1
    assert result["saturated_highlight_count"] == 0
    assert result["recommend_lower_key_energy"] is False


def test_preview_still_tool_reads_pixels_and_restores_image_colorspace(tmp_path):
    image_path = tmp_path / "preview.jpg"
    image_path.write_bytes(b"preview")

    class _Colorspace:
        name = "sRGB"

    class _Image:
        pixels = [0.95, 0.35, 0.15, 1.0]
        users = 0
        colorspace_settings = _Colorspace()

    class _Images:
        def __init__(self):
            self.image = _Image()
            self.removed = []

        def __iter__(self):
            return iter([])

        def load(self, path, check_existing=True):
            assert check_existing is False
            return self.image

        def remove(self, image):
            self.removed.append(image)

    images = _Images()
    bpy = SimpleNamespace(data=SimpleNamespace(images=images))
    result = load_and_call(
        "blender-photographic-lighting/scripts/analyze_photographic_test_still.py",
        bpy,
        image_path=str(image_path),
        highlight_threshold=0.7,
        warning_ratio=0.5,
    )

    assert result["success"] is True, result
    assert result["context"]["color_safety"]["recommend_lower_key_energy"] is True
    assert images.image.colorspace_settings.name == "sRGB"
    assert images.removed == [images.image]
