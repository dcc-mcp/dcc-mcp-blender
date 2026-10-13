"""Exercise format-dependent render configuration against native Blender RNA."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="requires a real Blender interpreter")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture
def scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


@pytest.mark.parametrize("depth,expected", [("16F", "16"), ("32F", "32"), ("32", "32")])
@pytest.mark.parametrize("container", [{"multilayer": True}, {"file_format": "OPEN_EXR"}])
def test_exr_depth_accepts_aliases_and_native_values(scene, depth, expected, container):
    mod = load_skill("blender-render", "set_render_output")

    result = mod.main(filepath="//output/shot", color_depth=depth, **container)

    assert result["success"] is True, result
    assert scene.render.image_settings.color_depth == expected
    assert result["context"]["applied"]["color_depth"] == expected
    assert scene.render.filepath == "//output/shot"


def test_multilayer_override_precedes_format_dependent_enums(scene):
    mod = load_skill("blender-render", "set_render_output")

    result = mod.main(file_format="JPEG", multilayer=True, color_mode="RGBA", color_depth="32F")

    assert result["success"] is True, result
    assert scene.render.image_settings.file_format == "OPEN_EXR_MULTILAYER"
    assert scene.render.image_settings.color_mode == "RGBA"
    assert scene.render.image_settings.color_depth == "32"


@pytest.mark.parametrize("invalid", [{"color_depth": "32F"}, {"color_mode": "RGBA"}])
def test_rejected_output_enum_restores_path_format_and_dependent_settings(scene, invalid):
    settings = scene.render.image_settings
    settings.file_format = "PNG"
    settings.color_mode = "RGBA"
    settings.color_depth = "16"
    scene.render.filepath = "//original"
    scene.render.use_single_layer = False
    mod = load_skill("blender-render", "set_render_output")

    result = mod.main(filepath="//changed", file_format="JPEG", multilayer=False, **invalid)

    assert result["success"] is False, result
    assert scene.render.filepath == "//original"
    assert settings.file_format == "PNG"
    assert settings.color_mode == "RGBA"
    assert settings.color_depth == "16"
    assert scene.render.use_single_layer is False
