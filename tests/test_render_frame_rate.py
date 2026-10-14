"""Render timebase validation, compatibility, and typed-tool contract."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tests.conftest import load_and_call, make_mock_bpy


@pytest.fixture
def bpy():
    render = SimpleNamespace(
        engine="CYCLES",
        resolution_x=1920,
        resolution_y=1080,
        resolution_percentage=100,
        fps=24,
        fps_base=1.0,
        filepath="//original",
        image_settings=SimpleNamespace(file_format="PNG"),
    )
    scene = SimpleNamespace(render=render, camera=None, cycles=SimpleNamespace(samples=64, device="CPU"))
    return SimpleNamespace(context=SimpleNamespace(scene=scene))


def _set(bpy, **kwargs):
    return load_and_call("blender-render/scripts/set_render_settings.py", bpy, **kwargs)


def _get(bpy):
    return load_and_call("blender-render/scripts/get_render_info.py", bpy)


def test_fractional_frame_rate_is_set_and_read_back(bpy):
    result = _set(bpy, fps=24, fps_base=1.001)

    assert result["success"] is True, result
    for context in (result["context"], _get(bpy)["context"]):
        assert context["fps"] == 24
        assert context["fps_base"] == 1.001
        assert context["effective_fps"] == pytest.approx(24000 / 1001)


def test_omitted_base_is_preserved_when_changing_fps(bpy):
    bpy.context.scene.render.fps_base = 1.001

    result = _set(bpy, fps=30)

    assert result["success"] is True, result
    assert bpy.context.scene.render.fps_base == 1.001
    assert result["context"]["fps_base"] == 1.001
    assert result["context"]["effective_fps"] == pytest.approx(30000 / 1001)


def test_base_can_change_without_changing_fps(bpy):
    bpy.context.scene.render.fps_base = 1.001

    result = _set(bpy, fps_base=1)

    assert result["success"] is True, result
    assert result["context"]["fps"] == 24
    assert result["context"]["fps_base"] == 1
    assert result["context"]["effective_fps"] == 24


def test_omitting_both_timebase_inputs_preserves_them(bpy):
    bpy.context.scene.render.fps = 30
    bpy.context.scene.render.fps_base = 1.001

    result = _set(bpy, resolution_x=640)

    assert result["success"] is True, result
    assert result["context"]["fps"] == 30
    assert result["context"]["fps_base"] == 1.001


@pytest.mark.parametrize(
    "fps", [True, False, 0, -1, 24.0, 23.976, "24", float("nan"), float("inf"), -float("inf"), 32768]
)
def test_invalid_fps_is_rejected_before_any_mutation(bpy, fps):
    before = copy.deepcopy(bpy.context.scene)

    result = _set(
        bpy,
        engine="BLENDER_WORKBENCH",
        resolution_x=640,
        resolution_y=360,
        resolution_percentage=50,
        fps=fps,
        fps_base=1.001,
        output_path="//changed",
        file_format="JPEG",
        samples=4,
    )

    assert result["success"] is False, result
    assert "fps" in str(result)
    assert bpy.context.scene == before


@pytest.mark.parametrize(
    "fps_base",
    [True, False, float("nan"), float("inf"), -float("inf"), 0, -1, 1e-6, 1000001, "1.001", 10**400],
)
def test_invalid_base_is_rejected_before_any_mutation(bpy, fps_base):
    before = copy.deepcopy(bpy.context.scene)

    result = _set(
        bpy,
        engine="BLENDER_WORKBENCH",
        resolution_x=640,
        resolution_y=360,
        resolution_percentage=50,
        fps=30,
        fps_base=fps_base,
        output_path="//changed",
        file_format="JPEG",
        samples=4,
    )

    assert result["success"] is False, result
    assert "fps_base" in str(result)
    assert bpy.context.scene == before


@pytest.mark.parametrize("kwargs", [{"fps": 49}, {"fps_base": 0.25}, {"fps_base": 3}])
def test_host_rna_bounds_are_checked_before_mutation(bpy, kwargs):
    bpy.context.scene.render.bl_rna = SimpleNamespace(
        properties={
            "fps": SimpleNamespace(hard_min=1, hard_max=48),
            "fps_base": SimpleNamespace(hard_min=0.5, hard_max=2.0),
        }
    )
    before = copy.deepcopy(bpy.context.scene)

    result = _set(bpy, resolution_x=640, **kwargs)

    assert result["success"] is False, result
    assert bpy.context.scene == before


@pytest.mark.parametrize("fps,fps_base", [(1, 1e-5), (32767, 1000000)])
def test_fallback_boundary_values_are_accepted(bpy, fps, fps_base):
    result = _set(bpy, fps=fps, fps_base=fps_base)

    assert result["success"] is True, result
    assert result["context"]["fps"] == fps
    assert result["context"]["fps_base"] == fps_base


def test_missing_base_is_reported_as_unknown_without_inventing_one(bpy):
    del bpy.context.scene.render.fps_base

    for result in (_get(bpy), _set(bpy, fps=30)):
        assert result["success"] is True, result
        assert result["context"]["fps_base"] is None
        assert result["context"]["effective_fps"] is None
    assert not hasattr(bpy.context.scene.render, "fps_base")


def test_unavailable_base_rejects_request_before_mutation(bpy):
    del bpy.context.scene.render.fps_base
    before = copy.deepcopy(bpy.context.scene)

    result = _set(bpy, resolution_x=640, fps=30, fps_base=1.001)

    assert result["success"] is False, result
    assert "unavailable" in str(result)
    assert bpy.context.scene == before


def test_legacy_magic_mock_does_not_fabricate_a_numeric_base():
    bpy = make_mock_bpy()

    for result in (_set(bpy, fps=30), _get(bpy)):
        assert result["success"] is True, result
        assert result["context"]["fps"] == 30
        assert result["context"]["fps_base"] is None
        assert result["context"]["effective_fps"] is None


def test_published_frame_rate_schema_has_no_resetting_defaults():
    path = Path(__file__).resolve().parents[1] / "src/dcc_mcp_blender/skills/blender-render/tools.yaml"
    tools = {tool["name"]: tool for tool in yaml.safe_load(path.read_text(encoding="utf-8"))["tools"]}
    schema = tools["set_render_settings"]["input_schema"]
    fps = schema["properties"]["fps"]
    base = schema["properties"]["fps_base"]
    assert fps["type"] == "integer"
    assert fps["minimum"] == 1
    assert fps["maximum"] == 32767
    assert base["type"] == "number"
    assert base["minimum"] == 9.999999747378752e-6
    assert base["maximum"] == 1000000
    assert "default" not in fps
    assert "default" not in base

    try:
        from dcc_mcp_core._core import ToolValidator
    except ImportError:
        pytest.skip("native core ToolValidator unavailable; schema round trip not exercised")

    validator = ToolValidator.from_schema_json(json.dumps(schema))
    for params in ({}, {"fps": 24}, {"fps_base": 1.001}, {"fps": 24, "fps_base": 1.001}, {"fps_base": base["minimum"]}):
        assert not validator.validate(json.dumps(params))[1], params
    for params in (
        {"fps": True},
        {"fps": 32768},
        {"fps_base": True},
        {"fps_base": 0},
        {"fps_base": -1},
        {"fps_base": 1e-6},
        {"fps_base": 1000001},
    ):
        assert validator.validate(json.dumps(params))[1], params
