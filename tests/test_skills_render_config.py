"""Unit tests for the blender-render configuration tools (bpy mocked)."""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.conftest import load_and_call, make_mock_bpy

RENDER_PATH = "src/dcc_mcp_blender/skills/blender-render/tools.yaml"
SKILL = "blender-render"


# ---------------------------------------------------------------------------
# Fake render scene
# ---------------------------------------------------------------------------


class FakeCycles:
    def __init__(self):
        self.use_denoising = False
        self.denoiser = "AUTO"
        self.denoising_input_passes = "RGB"
        self.denoising_prefilter = "ACCURATE"
        self.use_denoising_use_gpu = False
        self.use_pass_volume_direct = False
        self.use_pass_volume_indirect = False
        self.use_pass_denoising = False


class FakeViewLayer:
    def __init__(self, name="ViewLayer"):
        self.name = name
        self.use = True
        self.cycles = FakeCycles()
        self.pass_cryptomatte_depth = 6
        # Every ``use_pass_*`` flag starts disabled.
        for attribute in _LAYER_PASS_ATTRIBUTES:
            setattr(self, attribute, False)


class FakeViewLayerCollection:
    def __init__(self, layers):
        self._layers = list(layers)

    def get(self, name):
        for layer in self._layers:
            if layer.name == name:
                return layer
        return None

    def __iter__(self):
        return iter(self._layers)

    def __len__(self):
        return len(self._layers)

    def __contains__(self, name):
        return self.get(name) is not None


class FakeImageSettings:
    def __init__(self):
        self.file_format = "PNG"
        self.color_mode = "RGB"
        self.color_depth = "8"
        self.exr_codec = "ZIP"


class FakeRender:
    def __init__(self):
        self.engine = "CYCLES"
        self.resolution_x = 1920
        self.resolution_y = 1080
        self.resolution_percentage = 100
        self.filepath = "//render"
        self.fps = 24
        self.image_settings = FakeImageSettings()
        self.use_single_layer = True
        self.use_preview = False
        self.use_file_extension = True
        self.use_overwrite = True
        self.use_placeholder = False
        self.use_border = False
        self.border_min_x = 0.0
        self.border_min_y = 0.0
        self.border_max_x = 1.0
        self.border_max_y = 1.0


class FakeScene:
    def __init__(self, name="Scene", view_layers=None):
        self.name = name
        self.render = FakeRender()
        self.cycles = FakeCycles()
        self.view_layers = FakeViewLayerCollection(view_layers or [FakeViewLayer()])
        self.frame_start = 1
        self.frame_end = 250
        self.frame_step = 1
        self.frame_current = 1
        self.camera = None


class FakeSceneCollection:
    def __init__(self, scenes):
        self._scenes = list(scenes)

    def get(self, name):
        for scene in self._scenes:
            if scene.name == name:
                return scene
        return None

    def __iter__(self):
        return iter(self._scenes)

    def __len__(self):
        return len(self._scenes)


# Attributes the fake view layer exposes; mirrors the shared pass catalogue.
_LAYER_PASS_ATTRIBUTES = (
    "use_pass_combined",
    "use_pass_z",
    "use_pass_mist",
    "use_pass_normal",
    "use_pass_vector",
    "use_pass_diffuse_direct",
    "use_pass_diffuse_indirect",
    "use_pass_diffuse_color",
    "use_pass_glossy_direct",
    "use_pass_glossy_indirect",
    "use_pass_glossy_color",
    "use_pass_transmission_direct",
    "use_pass_transmission_indirect",
    "use_pass_transmission_color",
    "use_pass_emit",
    "use_pass_environment",
    "use_pass_position",
    "use_pass_object_index",
    "use_pass_material_index",
    "use_pass_ambient_occlusion",
    "use_pass_shadow",
    "use_pass_cryptomatte_object",
    "use_pass_cryptomatte_material",
    "use_pass_cryptomatte_asset",
)


def _bpy_with_scene(scene):
    bpy = make_mock_bpy()
    bpy.context.scene = scene
    bpy.data.scenes = FakeSceneCollection([scene])
    return bpy


def _call(script, bpy, **kwargs):
    return load_and_call(f"{SKILL}/scripts/{script}.py", bpy, **kwargs)


def _default_scene(name="Scene"):
    return FakeScene(name)


# ---------------------------------------------------------------------------
# View layer passes
# ---------------------------------------------------------------------------


def test_get_view_layer_passes_reports_enabled_passes():
    scene = _default_scene()
    layer = scene.view_layers.get("ViewLayer")
    layer.use_pass_z = True
    layer.use_pass_cryptomatte_object = True

    result = _call("get_view_layer_passes", _bpy_with_scene(scene))
    assert result["success"] is True
    assert result["context"]["enabled_passes"] == ["cryptomatte_object", "z"]
    assert result["context"]["passes"]["mist"] is False


def test_set_view_layer_passes_enables_and_disables():
    scene = _default_scene()
    layer = scene.view_layers.get("ViewLayer")
    layer.use_pass_z = True

    result = _call(
        "set_view_layer_passes",
        _bpy_with_scene(scene),
        enable=["normal", "mist"],
        disable=["z"],
    )
    assert result["success"] is True
    assert layer.use_pass_normal is True
    assert layer.use_pass_mist is True
    assert layer.use_pass_z is False
    assert result["context"]["enabled_passes"] == ["mist", "normal"]


def test_set_view_layer_passes_can_disable_a_pass_enabled_elsewhere():
    """configure_view_layer can only enable; this is the closing half."""
    scene = _default_scene()
    layer = scene.view_layers.get("ViewLayer")
    layer.use_pass_cryptomatte_material = True

    result = _call("set_view_layer_passes", _bpy_with_scene(scene), disable=["cryptomatte_material"])
    assert result["success"] is True
    assert layer.use_pass_cryptomatte_material is False
    assert result["context"]["enabled_passes"] == []


def test_set_view_layer_passes_reports_unknown_passes():
    result = _call("set_view_layer_passes", _bpy_with_scene(_default_scene()), enable=["nonsense"])
    assert result["success"] is False
    assert "unsupported" in result["message"].lower()


def test_set_view_layer_passes_requires_a_change():
    result = _call("set_view_layer_passes", _bpy_with_scene(_default_scene()))
    assert result["success"] is False
    assert "no pass changes" in result["message"].lower()


def test_set_view_layer_passes_targets_named_layer_and_scene():
    scene = _default_scene("Shot_010")
    scene.view_layers = FakeViewLayerCollection([FakeViewLayer("Beauty"), FakeViewLayer("AO")])

    result = _call(
        "set_view_layer_passes",
        _bpy_with_scene(scene),
        enable=["ambient_occlusion"],
        view_layer_name="AO",
        scene_name="Shot_010",
    )
    assert result["success"] is True
    assert result["context"]["view_layer_name"] == "AO"
    assert scene.view_layers.get("AO").use_pass_ambient_occlusion is True
    assert scene.view_layers.get("Beauty").use_pass_ambient_occlusion is False


def test_set_view_layer_passes_reports_unknown_layer():
    result = _call("set_view_layer_passes", _bpy_with_scene(_default_scene()), enable=["z"], view_layer_name="Ghost")
    assert result["success"] is False
    assert "view layer not found" in result["message"].lower()


def test_cycles_passes_route_to_the_cycles_owner():
    scene = _default_scene()
    layer = scene.view_layers.get("ViewLayer")

    result = _call("set_view_layer_passes", _bpy_with_scene(scene), enable=["volume_direct", "denoising"])
    assert result["success"] is True
    assert layer.cycles.use_pass_volume_direct is True
    assert layer.cycles.use_pass_denoising is True


# ---------------------------------------------------------------------------
# Denoise
# ---------------------------------------------------------------------------


def test_set_render_denoise_enables_and_flips_the_denoising_pass():
    scene = _default_scene()
    result = _call("set_render_denoise", _bpy_with_scene(scene), enabled=True)

    assert result["success"] is True
    assert scene.cycles.use_denoising is True
    assert scene.view_layers.get("ViewLayer").cycles.use_pass_denoising is True


def test_set_render_denoise_disables_and_clears_the_denoising_pass():
    scene = _default_scene()
    scene.cycles.use_denoising = True
    scene.view_layers.get("ViewLayer").cycles.use_pass_denoising = True

    result = _call("set_render_denoise", _bpy_with_scene(scene), enabled=False)
    assert result["success"] is True
    assert scene.cycles.use_denoising is False
    assert scene.view_layers.get("ViewLayer").cycles.use_pass_denoising is False


def test_set_render_denoise_configures_denoiser_and_input_passes():
    scene = _default_scene()
    result = _call(
        "set_render_denoise",
        _bpy_with_scene(scene),
        denoiser="openimagedenoise",
        input_passes="rgb_albedo_normal",
        prefilter="accurate",
        use_gpu=False,
    )

    assert result["success"] is True
    assert scene.cycles.denoiser == "OPENIMAGEDENOISE"
    assert scene.cycles.denoising_input_passes == "RGB_ALBEDO_NORMAL"
    assert scene.cycles.denoising_prefilter == "ACCURATE"


def test_set_render_denoise_rejects_unknown_denoiser():
    result = _call("set_render_denoise", _bpy_with_scene(_default_scene()), denoiser="MAGIC")
    assert result["success"] is False
    assert "unsupported denoiser" in result["message"].lower()


def test_set_render_denoise_requires_a_setting():
    result = _call("set_render_denoise", _bpy_with_scene(_default_scene()))
    assert result["success"] is False
    assert "no denoise settings" in result["message"].lower()


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def test_get_render_output_reports_current_state():
    result = _call("get_render_output", _bpy_with_scene(_default_scene()))
    assert result["success"] is True
    assert result["context"]["file_format"] == "PNG"
    assert result["context"]["multilayer"] is False


def test_set_render_output_configures_multilayer_exr():
    scene = _default_scene()
    result = _call(
        "set_render_output",
        _bpy_with_scene(scene),
        filepath="//out/shot_####",
        file_format="open_exr_multilayer",
        color_mode="rgba",
        color_depth="16",
        exr_codec="dwaa",
        multilayer=True,
    )

    assert result["success"] is True
    assert scene.render.filepath == "//out/shot_####"
    assert scene.render.image_settings.file_format == "OPEN_EXR_MULTILAYER"
    assert scene.render.image_settings.color_mode == "RGBA"
    assert scene.render.image_settings.color_depth == "16"
    assert scene.render.image_settings.exr_codec == "DWAA"
    assert scene.render.use_single_layer is False
    assert result["context"]["multilayer"] is True


def test_set_render_output_multilayer_false_uses_single_layer():
    scene = _default_scene()
    result = _call("set_render_output", _bpy_with_scene(scene), multilayer=False)
    assert result["success"] is True
    assert scene.render.use_single_layer is True
    assert result["context"]["multilayer"] is False


def test_set_render_output_rejects_unknown_format():
    result = _call("set_render_output", _bpy_with_scene(_default_scene()), file_format="GIF")
    assert result["success"] is False
    assert "unsupported output format" in result["message"].lower()


def test_set_render_output_rejects_unknown_exr_codec():
    result = _call("set_render_output", _bpy_with_scene(_default_scene()), exr_codec="LZMA")
    assert result["success"] is False
    assert "unsupported exr codec" in result["message"].lower()


def test_set_render_output_requires_a_setting():
    result = _call("set_render_output", _bpy_with_scene(_default_scene()))
    assert result["success"] is False
    assert "no output settings" in result["message"].lower()


# ---------------------------------------------------------------------------
# Render region
# ---------------------------------------------------------------------------


def test_set_render_region_enables_border():
    scene = _default_scene()
    result = _call("set_render_region", _bpy_with_scene(scene), min_x=0.2, min_y=0.3, max_x=0.8, max_y=0.9)

    assert result["success"] is True
    assert scene.render.use_border is True
    assert (scene.render.border_min_x, scene.render.border_min_y) == (0.2, 0.3)
    assert (scene.render.border_max_x, scene.render.border_max_y) == (0.8, 0.9)


def test_set_render_region_can_store_coordinates_without_enabling():
    scene = _default_scene()
    result = _call("set_render_region", _bpy_with_scene(scene), max_x=0.5, max_y=0.5, enabled=False)

    assert result["success"] is True
    assert scene.render.use_border is False
    assert scene.render.border_max_x == 0.5


def test_set_render_region_rejects_inverted_bounds():
    result = _call("set_render_region", _bpy_with_scene(_default_scene()), min_x=0.8, max_x=0.2)
    assert result["success"] is False
    assert "max_x must be greater" in result["error"].lower()


def test_set_render_region_rejects_out_of_range_values():
    result = _call("set_render_region", _bpy_with_scene(_default_scene()), min_x=-0.5)
    assert result["success"] is False
    assert "between 0 and 1" in result["error"].lower()


def test_set_render_region_rejects_non_numeric_values():
    result = _call("set_render_region", _bpy_with_scene(_default_scene()), min_x="left")
    assert result["success"] is False
    assert "must be numbers" in result["error"].lower()


def test_clear_render_region_resets_to_full_frame():
    scene = _default_scene()
    _call("set_render_region", _bpy_with_scene(scene), min_x=0.2, min_y=0.3, max_x=0.8, max_y=0.9)
    result = _call("clear_render_region", _bpy_with_scene(scene))

    assert result["success"] is True
    assert scene.render.use_border is False
    assert (scene.render.border_min_x, scene.render.border_min_y) == (0.0, 0.0)
    assert (scene.render.border_max_x, scene.render.border_max_y) == (1.0, 1.0)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def test_get_render_status_reports_frame_range_and_count():
    scene = _default_scene()
    scene.frame_start = 1001
    scene.frame_end = 1100
    scene.frame_step = 2

    result = _call("get_render_status", _bpy_with_scene(scene))
    assert result["success"] is True
    assert result["context"]["frame_start"] == 1001
    assert result["context"]["frame_end"] == 1100
    assert result["context"]["frame_count"] == 50


def test_get_render_status_surrounds_the_rest_of_the_plan():
    scene = _default_scene()
    scene.camera = type("Cam", (), {"name": "Camera_01"})()
    scene.view_layers.get("ViewLayer").use_pass_z = True
    _call("set_render_region", _bpy_with_scene(scene), min_x=0.1, max_x=0.6, min_y=0.1, max_y=0.6)

    result = _call("get_render_status", _bpy_with_scene(scene))
    context = result["context"]
    assert result["success"] is True
    assert context["active_camera"] == "Camera_01"
    assert context["has_active_camera"] is True
    assert context["enabled_passes"] == ["z"]
    assert context["border_enabled"] is True
    assert context["view_layer_count"] == 1
    assert context["multilayer"] is False


def test_get_render_status_flags_a_missing_camera():
    result = _call("get_render_status", _bpy_with_scene(_default_scene()))
    assert result["success"] is True
    assert result["context"]["has_active_camera"] is False


def test_get_render_status_targets_named_scene():
    scene = _default_scene("Shot_020")
    result = _call("get_render_status", _bpy_with_scene(scene), scene_name="Shot_020")
    assert result["success"] is True
    assert result["context"]["scene_name"] == "Shot_020"


def test_get_render_status_rejects_unknown_scene():
    result = _call("get_render_status", _bpy_with_scene(_default_scene()), scene_name="Missing")
    assert result["success"] is False
    assert "scene not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# Tool contract
# ---------------------------------------------------------------------------


def test_tools_yaml_declares_the_new_tools():
    doc = yaml.safe_load(Path(RENDER_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {
        "get_view_layer_passes",
        "set_view_layer_passes",
        "set_render_denoise",
        "get_render_output",
        "set_render_output",
        "set_render_region",
        "clear_render_region",
        "get_render_status",
    }.issubset(tools)


def test_new_tools_declare_required_contract_fields():
    doc = yaml.safe_load(Path(RENDER_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    for name in (
        "get_view_layer_passes",
        "set_view_layer_passes",
        "set_render_denoise",
        "get_render_output",
        "set_render_output",
        "set_render_region",
        "clear_render_region",
        "get_render_status",
    ):
        tool = tools[name]
        assert tool["execution"] == "sync", name
        assert tool["affinity"] == "main", name
        source = Path("src/dcc_mcp_blender/skills") / SKILL / tool["source_file"]
        assert source.is_file(), f"missing source script: {source}"


# ---------------------------------------------------------------------------
# Review regressions (PR #222)
# ---------------------------------------------------------------------------


def _scene_with_active_layer(active_layer, *others):
    scene = FakeScene()
    scene.view_layers = FakeViewLayerCollection([*others, active_layer])
    bpy = _bpy_with_scene(scene)
    bpy.context.view_layer = active_layer
    return scene, bpy


def test_multilayer_true_switches_the_container_format():
    """Multi-layer output is a container format, not a use_single_layer switch."""
    scene = _default_scene()
    result = _call("set_render_output", _bpy_with_scene(scene), multilayer=True)

    assert result["success"] is True
    assert scene.render.image_settings.file_format == "OPEN_EXR_MULTILAYER"
    assert scene.render.use_single_layer is False
    assert result["context"]["multilayer"] is True


def test_multilayer_false_downgrades_a_multilayer_container():
    scene = _default_scene()
    bpy = _bpy_with_scene(scene)
    _call("set_render_output", bpy, multilayer=True)
    result = _call("set_render_output", bpy, multilayer=False)

    assert result["success"] is True
    assert scene.render.image_settings.file_format == "OPEN_EXR"
    assert scene.render.use_single_layer is True
    assert result["context"]["multilayer"] is False


def test_multilayer_false_leaves_a_non_exr_container_alone():
    scene = _default_scene()
    result = _call("set_render_output", _bpy_with_scene(scene), multilayer=False)

    assert result["success"] is True
    assert scene.render.image_settings.file_format == "PNG"
    assert result["context"]["multilayer"] is False


def test_read_tools_derive_multilayer_from_the_format():
    """use_single_layer alone must not be reported as multi-layer output."""
    scene = _default_scene()
    scene.render.use_single_layer = False
    bpy = _bpy_with_scene(scene)

    readout = _call("get_render_output", bpy)
    status = _call("get_render_status", bpy)
    assert readout["context"]["multilayer"] is False
    assert status["context"]["multilayer"] is False

    _call("set_render_output", bpy, multilayer=True)
    assert _call("get_render_output", bpy)["context"]["multilayer"] is True
    assert _call("get_render_status", bpy)["context"]["multilayer"] is True


def test_active_view_layer_wins_over_the_default_name():
    active = FakeViewLayer("ShotCam")
    active.use_pass_z = True
    scene, bpy = _scene_with_active_layer(active, FakeViewLayer("ViewLayer"))

    result = _call("get_view_layer_passes", bpy)
    assert result["success"] is True
    assert result["context"]["view_layer_name"] == "ShotCam"
    assert result["context"]["enabled_passes"] == ["z"]


def test_set_view_layer_passes_writes_the_active_layer():
    active = FakeViewLayer("ShotCam")
    other = FakeViewLayer("ViewLayer")
    _scene, bpy = _scene_with_active_layer(active, other)

    result = _call("set_view_layer_passes", bpy, enable=["mist"])
    assert result["success"] is True
    assert result["context"]["view_layer_name"] == "ShotCam"
    assert active.use_pass_mist is True
    assert other.use_pass_mist is False


def test_named_scene_does_not_use_the_context_view_layer():
    """The context view layer may belong to a different scene."""
    other_scene = FakeScene("Other")
    other_scene.view_layers = FakeViewLayerCollection([FakeViewLayer("ViewLayer")])
    active = FakeViewLayer("ShotCam")
    _scene, bpy = _scene_with_active_layer(active, FakeViewLayer("ViewLayer"))

    result = _call("set_view_layer_passes", bpy, scene_name="Scene", enable=["mist"])
    assert result["success"] is True
    assert result["context"]["view_layer_name"] == "ViewLayer"


def test_unavailable_pass_leaves_the_batch_unapplied():
    """A rejected batch must not partially mutate the scene."""
    scene = _default_scene()
    layer = scene.view_layers.get("ViewLayer")
    layer.cycles = None

    result = _call("set_view_layer_passes", _bpy_with_scene(scene), enable=["combined", "denoising"])
    assert result["success"] is False
    assert layer.use_pass_combined is False, "nothing may be written before preflight passes"
    assert "nothing was changed" in result["error"].lower() or "no passes were changed" in result["error"].lower()


def test_missing_cycles_is_distinguished_from_an_old_blender_build():
    scene = _default_scene()
    scene.view_layers.get("ViewLayer").cycles = None
    result = _call("set_view_layer_passes", _bpy_with_scene(scene), enable=["denoising"])

    assert result["success"] is False
    assert "cycles is not available" in result["error"].lower()


def test_unavailable_output_setting_leaves_the_batch_unapplied():
    scene = _default_scene()
    del scene.render.image_settings.color_mode

    result = _call(
        "set_render_output",
        _bpy_with_scene(scene),
        filepath="//out/v1",
        file_format="OPEN_EXR",
        color_mode="RGB",
    )
    assert result["success"] is False
    assert scene.render.filepath == "//render", "nothing may be written before preflight passes"
    assert "image_settings.color_mode" in result["error"]


def test_unavailable_denoise_setting_leaves_the_batch_unapplied():
    scene = _default_scene()
    del scene.cycles.denoiser

    result = _call("set_render_denoise", _bpy_with_scene(scene), enabled=True, denoiser="OPTIX")
    assert result["success"] is False
    assert scene.cycles.use_denoising is False, "nothing may be written before preflight passes"
    assert "cycles.denoiser" in result["error"]


def test_get_render_status_reports_an_unknown_view_layer():
    result = _call("get_render_status", _bpy_with_scene(_default_scene()), view_layer_name="Ghost")
    assert result["success"] is False
    assert "view layer not found" in result["message"].lower()


def test_enable_and_disable_intersection_is_rejected():
    scene = _default_scene()
    result = _call("set_view_layer_passes", _bpy_with_scene(scene), enable=["z"], disable=["z"])

    assert result["success"] is False
    assert "both enable and disable" in result["error"].lower()
    assert scene.view_layers.get("ViewLayer").use_pass_z is False


def test_preflight_probes_each_property_on_its_own_host():
    """The host object must be explicit, not derived from the path string.

    ``use_single_layer`` lives on ``render`` while the others live on
    ``render.image_settings``. Deriving the host from the path gives two sources
    of truth that can drift, and a drifted host rejects a usable property while
    blaming the Blender build.
    """
    scene = _default_scene()

    # use_single_layer is present on render and must not be reported missing.
    result = _call("set_render_output", _bpy_with_scene(scene), multilayer=True)
    assert result["success"] is True
    assert scene.render.use_single_layer is False

    # A property missing from render is still rejected without touching anything.
    scene = _default_scene()
    del scene.render.use_single_layer
    result = _call("set_render_output", _bpy_with_scene(scene), multilayer=True)
    assert result["success"] is False
    assert scene.render.image_settings.file_format == "PNG"
    assert "use_single_layer" in result["error"]

    # A property missing from image_settings is rejected by name.
    scene = _default_scene()
    del scene.render.image_settings.color_mode
    result = _call("set_render_output", _bpy_with_scene(scene), color_mode="RGB")
    assert result["success"] is False
    assert "image_settings.color_mode" in result["error"]
