"""Tests for the photographic Cycles render-profile skill."""

from __future__ import annotations

from types import SimpleNamespace

import yaml

from tests.conftest import load_and_call

SKILL_DIR = "blender-render-profile"


class _ViewLayers(list):
    def get(self, name):
        return next((layer for layer in self if layer.name == name), None)


class _ImageSettings:
    def __init__(self):
        self.file_format = "PNG"
        self.color_mode = "RGB"
        self.color_depth = "8"
        self.quality = 75
        self.media_type = "IMAGE"


class _Render:
    def __init__(self):
        self.engine = "BLENDER_EEVEE_NEXT"
        self.resolution_x = 1920
        self.resolution_y = 1080
        self.resolution_percentage = 100
        self.fps = 30
        self.fps_base = 1.0
        self.filter_size = 1.0
        self.use_motion_blur = False
        self.motion_blur_shutter = 0.25
        self.motion_blur_position = "CENTER"
        self.use_persistent_data = False
        self.image_settings = _ImageSettings()


class _Cycles:
    def __init__(self):
        self.device = "CPU"
        self.samples = 16
        self.use_adaptive_sampling = False
        self.adaptive_threshold = 0.1
        self.use_denoising = False
        self.denoiser = "AUTO"
        self.denoising_input_passes = "RGB"
        self.denoising_prefilter = "FAST"
        self.denoising_use_gpu = True
        self.max_bounces = 12
        self.diffuse_bounces = 3
        self.glossy_bounces = 3
        self.transmission_bounces = 3
        self.transparent_max_bounces = 8
        self.sample_clamp_direct = 1.0
        self.sample_clamp_indirect = 10.0
        self.caustics_reflective = True
        self.caustics_refractive = True
        self.blur_glossy = 0.0
        self.filter_width = 1.0


class _LayerCycles:
    def __init__(self):
        self.denoising_store_passes = False


class _ViewLayer:
    def __init__(self, name="ViewLayer"):
        self.name = name
        self.cycles = _LayerCycles()


class _Scene:
    def __init__(self, name="Scene"):
        self.name = name
        self.render = _Render()
        self.cycles = _Cycles()
        self.view_layers = _ViewLayers([_ViewLayer()])
        self.view_settings = SimpleNamespace(
            view_transform="Standard",
            look="None",
            exposure=1.0,
        )


class _Device:
    def __init__(self, name, device_type, use=False):
        self.name = name
        self.type = device_type
        self.use = use


class _Preferences:
    def __init__(self, devices=()):
        self.compute_device_type = "NONE"
        self.devices = list(devices)

    def get_devices(self):
        return None


class _Scenes(list):
    def get(self, name):
        return next((scene for scene in self if scene.name == name), None)


def _bpy(scene=None, preferences=None, version=(5, 2, 1)):
    scene = scene or _Scene()
    preferences = preferences if preferences is not None else _Preferences()
    return SimpleNamespace(
        app=SimpleNamespace(version=version, version_string="5.2.1"),
        context=SimpleNamespace(
            scene=scene,
            preferences=SimpleNamespace(addons={"cycles": SimpleNamespace(preferences=preferences)}),
        ),
        data=SimpleNamespace(scenes=_Scenes([scene])),
    )


def _call(script, bpy, **kwargs):
    return load_and_call(f"{SKILL_DIR}/scripts/{script}.py", bpy, **kwargs)


def test_profile_defaults_match_preview_and_final_contract():
    from dcc_mcp_blender._render_profile_ops import _profile_values

    preview = _profile_values("preview", "exterior", None)
    interior = _profile_values("FINAL", "INTERIOR", None)
    exterior = _profile_values("FINAL", "EXTERIOR", None)

    assert (preview["resolution_percentage"], preview["samples"]) == (25, 32)
    assert (exterior["resolution_percentage"], exterior["samples"]) == (100, 64)
    assert interior["samples"] == 112
    assert preview["motion_blur_shutter"] == 0.5
    assert preview["denoising_input_passes"] == "RGB_ALBEDO_NORMAL"


def test_apply_profile_selects_requested_gpu_and_configures_scene():
    scene = _Scene()
    cuda = _Device("RTX", "CUDA")
    bpy = _bpy(scene, _Preferences([cuda]))

    result = _call(
        "apply_render_profile",
        bpy,
        profile_name="FINAL",
        scene_kind="EXTERIOR",
        device_backend="CUDA",
        allow_cpu_fallback=False,
    )

    assert result["success"] is True, result
    assert result["context"]["resolved_device_backend"] == "CUDA"
    assert scene.render.engine == "CYCLES"
    assert scene.render.resolution_percentage == 100
    assert scene.cycles.samples == 64
    assert scene.cycles.device == "GPU"
    assert bpy.context.preferences.addons["cycles"].preferences.compute_device_type == "CUDA"
    assert cuda.use is True
    assert scene.render.image_settings.file_format == "JPEG"
    assert scene.render.image_settings.quality == 96


def test_apply_profile_allows_cpu_without_cycles_preferences():
    scene = _Scene()
    bpy = _bpy(scene, preferences=None)
    bpy.context.preferences.addons = {}

    result = _call("apply_render_profile", bpy, profile_name="PREVIEW", device_backend="CPU")

    assert result["success"] is True, result
    assert result["context"]["resolved_device_backend"] == "CPU"
    assert scene.cycles.device == "CPU"
    assert scene.render.resolution_percentage == 25


def test_auto_backend_can_fall_back_to_cpu_and_reports_when_disabled():
    from dcc_mcp_blender._render_profile_ops import _resolve_device_backend

    assert _resolve_device_backend("AUTO", [], True) == ("CPU", True)
    try:
        _resolve_device_backend("AUTO", [], False)
    except ValueError as exc:
        assert "fallback" in str(exc).lower()
    else:
        raise AssertionError("CPU fallback should be rejected when disabled")


def test_unavailable_explicit_gpu_is_rejected_before_scene_mutation():
    scene = _Scene()
    bpy = _bpy(scene)
    before = (scene.render.engine, scene.render.resolution_percentage, scene.cycles.samples)

    result = _call(
        "apply_render_profile",
        bpy,
        profile_name="FINAL",
        device_backend="OPTIX",
        allow_cpu_fallback=False,
    )

    assert result["success"] is False
    assert "unavailable" in result["message"].lower()
    assert (scene.render.engine, scene.render.resolution_percentage, scene.cycles.samples) == before


def test_validation_is_read_only_and_reports_all_profile_fields():
    scene = _Scene()
    bpy = _bpy(scene)
    before = (
        scene.render.engine,
        scene.render.image_settings.file_format,
        scene.cycles.samples,
        scene.view_settings.view_transform,
    )

    result = _call("validate_render_profile", bpy, profile_name="FINAL", device_backend="CPU")

    assert result["success"] is True
    assert result["context"]["valid"] is False
    fields = {issue["field"] for issue in result["context"]["issues"]}
    assert {"engine", "samples", "file_format", "view_transform", "filter_width"}.issubset(fields)
    assert (
        scene.render.engine,
        scene.render.image_settings.file_format,
        scene.cycles.samples,
        scene.view_settings.view_transform,
    ) == before


def test_apply_failure_rolls_back_image_format_and_scene_settings():
    scene = _Scene()
    preferences = _Preferences()
    bpy = _bpy(scene, preferences)
    initial = (scene.render.image_settings.file_format, scene.render.resolution_percentage)

    class _BrokenCycles(_Cycles):
        def __setattr__(self, name, value):
            if name == "filter_width" and value == 1.5:
                object.__setattr__(self, name, 0.3)
                return
            object.__setattr__(self, name, value)

    scene.cycles = _BrokenCycles()
    result = _call("apply_render_profile", bpy, profile_name="FINAL", device_backend="CPU")

    assert result["success"] is False
    assert (scene.render.image_settings.file_format, scene.render.resolution_percentage) == initial


def test_tools_yaml_declares_the_profile_contract():
    from pathlib import Path

    doc = yaml.safe_load(
        Path("src/dcc_mcp_blender/skills/blender-render-profile/tools.yaml").read_text(encoding="utf-8")
    )
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert set(tools) == {
        "get_render_capabilities",
        "apply_render_profile",
        "get_render_profile",
        "validate_render_profile",
    }
    assert tools["apply_render_profile"]["input_schema"]["properties"]["device_backend"]["enum"][-1] == "CPU"
