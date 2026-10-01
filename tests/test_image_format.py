"""Model Blender's media-dependent enum, without claiming native acceptance."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from dcc_mcp_blender import _render_job_ops as jobs
from dcc_mcp_blender._image_format import image_format, set_image_format, worker_format_expression
from tests.conftest import load_and_call
from tests.test_skills_render_config import _bpy_with_scene, _default_scene


class MediaImageSettings:
    def __init__(self):
        self._media_type = "IMAGE"
        self._file_format = "PNG"
        self.events = []
        self.color_mode = "RGB"
        self.color_depth = "8"
        self.exr_codec = "ZIP"
        self.use_preview = False

    @property
    def media_type(self):
        return self._media_type

    @media_type.setter
    def media_type(self, value):
        assert value in {"IMAGE", "MULTI_LAYER_IMAGE", "VIDEO"}
        self.events.append(("media_type", value))
        self._media_type = value
        if value == "MULTI_LAYER_IMAGE":
            self._file_format = "OPEN_EXR_MULTILAYER"
        elif self._file_format == "OPEN_EXR_MULTILAYER":
            self._file_format = "PNG"

    @property
    def file_format(self):
        return self._file_format

    @file_format.setter
    def file_format(self, value):
        accepted = {"OPEN_EXR_MULTILAYER"} if self._media_type == "MULTI_LAYER_IMAGE" else {"PNG", "OPEN_EXR", "JPEG"}
        if value not in accepted:
            raise TypeError("enum not found in the current media type")
        self.events.append(("file_format", value))
        self._file_format = value


@pytest.mark.parametrize("name", ["PNG", "OPEN_EXR", "OPEN_EXR_MULTILAYER"])
def test_dynamic_media_type_is_set_before_file_format_in_both_directions(name):
    settings = MediaImageSettings()
    with pytest.raises(TypeError):
        settings.file_format = "OPEN_EXR_MULTILAYER"
    set_image_format(settings, "OPEN_EXR_MULTILAYER")
    settings.events.clear()
    set_image_format(settings, name)
    assert settings.events == [
        ("media_type", "MULTI_LAYER_IMAGE" if name == "OPEN_EXR_MULTILAYER" else "IMAGE"),
        ("file_format", name),
    ]
    assert image_format(settings) == name


def test_legacy_host_has_no_media_type_added():
    settings = SimpleNamespace(file_format="PNG")
    set_image_format(settings, "OPEN_EXR_MULTILAYER")
    assert settings.file_format == "OPEN_EXR_MULTILAYER"
    assert not hasattr(settings, "media_type")


def test_rejected_format_restores_original_media_and_container():
    settings = MediaImageSettings()
    set_image_format(settings, "OPEN_EXR_MULTILAYER")
    with pytest.raises(TypeError):
        set_image_format(settings, "UNAVAILABLE")
    assert settings.media_type == "MULTI_LAYER_IMAGE"
    assert settings.file_format == "OPEN_EXR_MULTILAYER"


def test_typed_output_and_settings_use_the_same_media_transition():
    scene = _default_scene()
    settings = scene.render.image_settings = MediaImageSettings()
    bpy = _bpy_with_scene(scene)
    result = load_and_call("blender-render/scripts/set_render_output.py", bpy, multilayer=True)
    assert result["success"] is True
    assert settings.media_type == "MULTI_LAYER_IMAGE" and scene.render.use_single_layer is False
    result = load_and_call("blender-render/scripts/set_render_settings.py", bpy, file_format="PNG")
    assert result["success"] is True
    assert settings.media_type == "IMAGE" and settings.file_format == "PNG"
    result = load_and_call("blender-render/scripts/set_render_output.py", bpy, file_format="OPEN_EXR_MULTILAYER")
    assert result["success"] is True
    result = load_and_call("blender-render/scripts/set_render_output.py", bpy, multilayer=False)
    assert result["success"] is True
    assert settings.media_type == "IMAGE" and settings.file_format == "OPEN_EXR"


@pytest.mark.parametrize("name", ["PNG", "OPEN_EXR", "OPEN_EXR_MULTILAYER"])
def test_detached_worker_configures_native_settings_before_render(monkeypatch, name):
    settings = MediaImageSettings()
    set_image_format(settings, "OPEN_EXR_MULTILAYER")
    bpy = SimpleNamespace(
        context=SimpleNamespace(scene=SimpleNamespace(render=SimpleNamespace(image_settings=settings)))
    )
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    command = jobs._build_blender_command(
        blender_path="blender",
        scene_path="scene.blend",
        output_pattern="beauty_####",
        frames=[1],
        factory_startup=False,
        output_format=name,
    )
    assert "--render-format" not in command
    assert command[command.index("--python-exit-code") + 1] == "1"
    assert command.index("--python-expr") < command.index("--render-frame")
    expression = command[command.index("--python-expr") + 1]
    exec(expression, {})
    assert image_format(settings) == name
    assert jobs._scene_file_format() == name


def test_format_expression_embeds_data_literal_not_executable_code(monkeypatch):
    settings = SimpleNamespace(file_format="PNG")
    bpy = SimpleNamespace(
        context=SimpleNamespace(scene=SimpleNamespace(render=SimpleNamespace(image_settings=settings)))
    )
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    requested = "PNG'; raise RuntimeError('injected') #"
    exec(worker_format_expression(requested), {})
    assert settings.file_format == requested.upper()
