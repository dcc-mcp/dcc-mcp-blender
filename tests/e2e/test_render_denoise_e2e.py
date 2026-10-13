"""Verify denoise settings against native Cycles RNA without rendering."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="requires a real Blender interpreter")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture
def scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


@pytest.mark.parametrize("use_gpu", [False, True])
def test_set_render_denoise_gpu_uses_native_rna(scene, use_gpu):
    """Both values must change real RNA, even on a host without a GPU."""
    scene.cycles.denoising_use_gpu = not use_gpu
    mod = load_skill("blender-render", "set_render_denoise")

    result = mod.main(use_gpu=use_gpu)

    assert result["success"] is True, result
    assert scene.cycles.denoising_use_gpu is use_gpu
    assert result["context"]["applied"] == {"denoising_use_gpu": use_gpu}


def test_set_render_denoise_accepts_showcase_cpu_settings(scene):
    mod = load_skill("blender-render", "set_render_denoise")
    scene.cycles.denoising_use_gpu = True
    scene.cycles.use_denoising = False

    result = mod.main(
        enabled=True,
        denoiser="OPENIMAGEDENOISE",
        input_passes="RGB_ALBEDO_NORMAL",
        prefilter="ACCURATE",
        use_gpu=False,
    )

    assert result["success"] is True, result
    assert scene.cycles.use_denoising is True
    assert scene.cycles.denoiser == "OPENIMAGEDENOISE"
    assert scene.cycles.denoising_input_passes == "RGB_ALBEDO_NORMAL"
    assert scene.cycles.denoising_prefilter == "ACCURATE"
    assert scene.cycles.denoising_use_gpu is False


def test_set_render_denoise_missing_scene_does_not_change_active_scene(scene):
    mod = load_skill("blender-render", "set_render_denoise")
    scene.cycles.denoising_use_gpu = True
    scene.cycles.use_denoising = False

    result = mod.main(enabled=True, use_gpu=False, scene_name="MissingDenoiseScene")

    assert result["success"] is False
    assert scene.cycles.use_denoising is False
    assert scene.cycles.denoising_use_gpu is True


@pytest.mark.parametrize("enabled", [False, True])
def test_set_render_denoise_updates_native_store_passes(scene, enabled):
    layer = bpy.context.view_layer
    layer.cycles.denoising_store_passes = not enabled
    mod = load_skill("blender-render", "set_render_denoise")

    result = mod.main(enabled=enabled)

    assert result["success"] is True, result
    assert layer.cycles.denoising_store_passes is enabled


@pytest.mark.parametrize("enabled", [False, True])
def test_set_view_layer_denoising_pass_uses_native_rna(scene, enabled):
    layer = bpy.context.view_layer
    layer.cycles.denoising_store_passes = not enabled
    mod = load_skill("blender-render", "set_view_layer_passes")

    result = mod.main(**{"enable" if enabled else "disable": ["denoising"]})

    assert result["success"] is True, result
    assert layer.cycles.denoising_store_passes is enabled
    read = load_skill("blender-render", "get_view_layer_passes").main()
    assert read["context"]["passes"]["denoising"] is enabled


def test_scene_assembly_uses_same_native_denoising_pass(scene):
    layer = bpy.context.view_layer
    layer.cycles.denoising_store_passes = False
    mod = load_skill("blender-scene-assembly", "configure_view_layer")

    result = mod.main(name=layer.name, passes=["denoising"])

    assert result["success"] is True, result
    assert layer.cycles.denoising_store_passes is True


def test_rejected_denoise_enum_restores_previous_settings(scene):
    scene.cycles.use_denoising = False
    scene.cycles.denoising_input_passes = "RGB"
    scene.cycles.denoising_prefilter = "FAST"
    bpy.context.view_layer.cycles.denoising_store_passes = False
    mod = load_skill("blender-render", "set_render_denoise")

    result = mod.main(enabled=True, input_passes="RGB_ALBEDO_NORMAL", prefilter="INVALID")

    assert result["success"] is False, result
    assert scene.cycles.use_denoising is False
    assert scene.cycles.denoising_input_passes == "RGB"
    assert scene.cycles.denoising_prefilter == "FAST"
    assert bpy.context.view_layer.cycles.denoising_store_passes is False
