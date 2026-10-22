"""Mock-only CPU render thread tests; these do not establish native Blender acceptance."""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tests.conftest import load_and_call, load_skill_script, make_mock_bpy


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
        threads_mode="AUTO",
        threads=2,
        bl_rna=SimpleNamespace(
            properties={
                "threads_mode": SimpleNamespace(
                    type="ENUM",
                    is_readonly=False,
                    enum_items=[SimpleNamespace(identifier=x) for x in ("AUTO", "FIXED")],
                ),
                "threads": SimpleNamespace(type="INT", is_readonly=False, hard_min=1, hard_max=16),
            }
        ),
    )
    scene = SimpleNamespace(render=render, camera=None, cycles=SimpleNamespace(samples=64, device="CPU"))
    return SimpleNamespace(context=SimpleNamespace(scene=scene))


def _set(bpy, **kwargs):
    return load_and_call("blender-render/scripts/set_render_settings.py", bpy, **kwargs)


def _get(bpy):
    return load_and_call("blender-render/scripts/get_render_info.py", bpy)


def _assert_readback(bpy, result, mode, threads):
    assert result["success"] is True, result
    read = _get(bpy)
    assert read["success"] is True, read
    for context in (result["context"], read["context"]):
        assert context["threads_mode"] == bpy.context.scene.render.threads_mode == mode
        assert context["threads"] == bpy.context.scene.render.threads == threads


def _reject_without_mutation(bpy, **params):
    before = copy.deepcopy(bpy.context.scene)
    result = _set(
        bpy,
        engine="BLENDER_WORKBENCH",
        resolution_x=640,
        resolution_y=360,
        resolution_percentage=50,
        fps=30,
        fps_base=1.001,
        output_path="//changed",
        file_format="JPEG",
        samples=4,
        **params,
    )
    assert result["success"] is False, result
    assert bpy.context.scene == before
    return result


@pytest.mark.parametrize("mode", ["AUTO", "FIXED"])
def test_omitting_thread_inputs_preserves_existing_settings(bpy, mode):
    bpy.context.scene.render.threads_mode = mode
    _assert_readback(bpy, _set(bpy, resolution_x=640), mode, 2)
    assert bpy.context.scene.render.resolution_x == 640


@pytest.mark.parametrize("params", [{"threads": 4}, {"threads_mode": "FIXED", "threads": 4}])
def test_count_selects_fixed_and_returns_native_fields(bpy, params):
    _assert_readback(bpy, _set(bpy, **params), "FIXED", 4)


def test_switch_fixed_to_auto_does_not_assign_the_fixed_count(bpy):
    _assert_readback(bpy, _set(bpy, threads=4), "FIXED", 4)
    _assert_readback(bpy, _set(bpy, threads_mode="AUTO"), "AUTO", 4)
    _assert_readback(bpy, _set(bpy, threads_mode="FIXED", threads=2), "FIXED", 2)


@pytest.mark.parametrize("count", [1, 16])
def test_native_rna_boundaries_are_accepted(bpy, count):
    _assert_readback(bpy, _set(bpy, threads=count), "FIXED", count)


@pytest.mark.parametrize(
    "count",
    [True, False, 0, -1, 2.0, 2.5, "2", float("nan"), float("inf"), -float("inf"), 17, 10**400, [], {}],
)
def test_invalid_count_rejects_before_any_mutation(bpy, count):
    result = _reject_without_mutation(bpy, threads=count)
    assert "threads" in str(result)


@pytest.mark.parametrize("mode", [True, False, 2, "auto", "fixed", "", "INVALID", [], {}])
def test_invalid_mode_rejects_before_any_mutation(bpy, mode):
    result = _reject_without_mutation(bpy, threads_mode=mode)
    assert "threads_mode" in str(result)


@pytest.mark.parametrize("params", [{"threads_mode": "AUTO", "threads": 2}, {"threads_mode": "FIXED"}])
def test_inconsistent_request_rejects_before_any_mutation(bpy, params):
    _reject_without_mutation(bpy, **params)


@pytest.mark.parametrize("count", [1, 9])
def test_actual_host_bounds_override_generic_positive_schema(bpy, count):
    prop = bpy.context.scene.render.bl_rna.properties["threads"]
    prop.hard_min, prop.hard_max = 2, 8
    _reject_without_mutation(bpy, threads=count)


@pytest.mark.parametrize("name", ["threads_mode", "threads"])
def test_missing_rna_property_rejects_before_mutation(bpy, name):
    del bpy.context.scene.render.bl_rna.properties[name]
    _reject_without_mutation(bpy, threads=4)


@pytest.mark.parametrize("name", ["threads_mode", "threads"])
def test_missing_native_value_rejects_before_mutation(bpy, name):
    delattr(bpy.context.scene.render, name)
    _reject_without_mutation(bpy, threads=4)


def test_missing_rna_metadata_rejects_before_mutation(bpy):
    del bpy.context.scene.render.bl_rna
    _reject_without_mutation(bpy, threads=4)


@pytest.mark.parametrize("name", ["threads_mode", "threads"])
def test_static_readonly_rejects_before_mutation(bpy, name):
    bpy.context.scene.render.bl_rna.properties[name].is_readonly = True
    _reject_without_mutation(bpy, threads=4)


@pytest.mark.parametrize("name", ["threads_mode", "threads"])
def test_instance_readonly_rejects_before_mutation(bpy, name):
    bpy.context.scene.render.is_property_readonly = lambda field: field == name
    _reject_without_mutation(bpy, threads=4)


@pytest.mark.parametrize("name,wrong_type", [("threads_mode", "STRING"), ("threads", "FLOAT")])
def test_wrong_native_property_type_rejects_before_mutation(bpy, name, wrong_type):
    bpy.context.scene.render.bl_rna.properties[name].type = wrong_type
    _reject_without_mutation(bpy, threads=4)


@pytest.mark.parametrize("lower,upper", [(None, 16), (1, None), (True, 16), (1, False), (1.0, 16), (0, 16), (2, 1)])
def test_invalid_rna_bounds_fail_closed(bpy, lower, upper):
    prop = bpy.context.scene.render.bl_rna.properties["threads"]
    prop.hard_min, prop.hard_max = lower, upper
    _reject_without_mutation(bpy, threads=4)


@pytest.mark.parametrize("mode,params", [("AUTO", {"threads": 4}), ("FIXED", {"threads_mode": "AUTO"})])
def test_requested_enum_must_exist_in_native_rna(bpy, mode, params):
    bpy.context.scene.render.bl_rna.properties["threads_mode"].enum_items = [SimpleNamespace(identifier=mode)]
    _reject_without_mutation(bpy, **params)


def test_auto_does_not_require_or_write_the_inactive_count_property(bpy):
    bpy.context.scene.render.threads_mode = "FIXED"
    bpy.context.scene.render.bl_rna.properties["threads"].is_readonly = True
    _assert_readback(bpy, _set(bpy, threads_mode="AUTO"), "AUTO", 2)


def test_unavailable_thread_fields_do_not_break_legacy_calls(bpy):
    render = bpy.context.scene.render
    del render.threads_mode, render.threads, render.bl_rna
    for result in (_set(bpy, resolution_x=640), _get(bpy)):
        assert result["success"] is True, result
        assert result["context"]["threads_mode"] is None
        assert result["context"]["threads"] is None
    assert not hasattr(render, "threads_mode")
    assert not hasattr(render, "threads")


def test_magic_mock_readback_does_not_fabricate_thread_values():
    bpy = make_mock_bpy()
    for result in (_set(bpy, resolution_x=640), _get(bpy)):
        assert result["success"] is True, result
        assert result["context"]["threads_mode"] is None
        assert result["context"]["threads"] is None
        json.dumps({key: result["context"][key] for key in ("threads_mode", "threads")})


def test_direct_python_none_preserves_optional_parameter_convention(bpy):
    _assert_readback(bpy, _set(bpy, threads_mode=None, threads=None), "AUTO", 2)


@pytest.mark.parametrize("failure", ["reject_count", "clamp_count", "reject_mode", "ignore_mode"])
def test_host_assignment_failure_reports_readback_before_other_mutations(bpy, failure):
    class RejectingRender(SimpleNamespace):
        def __setattr__(self, name, value):
            if name == "threads" and value == 4:
                if failure == "reject_count":
                    raise ValueError("host rejected count")
                if failure == "clamp_count":
                    value = 3
            if name == "threads_mode" and value == "FIXED":
                if failure == "reject_mode":
                    raise ValueError("host rejected mode")
                if failure == "ignore_mode":
                    return
            super().__setattr__(name, value)

    bpy.context.scene.render = RejectingRender(**vars(bpy.context.scene.render))
    result = _set(bpy, resolution_x=640, threads=4)
    render = bpy.context.scene.render
    assert result["success"] is False, result
    assert render.resolution_x == 1920
    assert result["context"]["thread_settings_may_have_changed"] is True
    assert result["context"]["threads"] == render.threads
    assert result["context"]["threads_mode"] == render.threads_mode


def test_invalid_existing_engine_does_not_apply_threads(bpy):
    before = copy.deepcopy(bpy.context.scene)
    result = _set(bpy, engine="INVALID_ENGINE", threads=4)
    assert result["success"] is False, result
    assert bpy.context.scene == before


def test_existing_positional_argument_order_is_unchanged():
    setter = load_skill_script("blender-render", "set_render_settings").set_render_settings
    assert list(inspect.signature(setter).parameters) == [
        "engine",
        "resolution_x",
        "resolution_y",
        "resolution_percentage",
        "fps",
        "samples",
        "output_path",
        "file_format",
        "fps_base",
        "threads_mode",
        "threads",
    ]


def test_published_thread_schema_and_actual_core_validator():
    path = Path(__file__).resolve().parents[1] / "src/dcc_mcp_blender/skills/blender-render/tools.yaml"
    tools = {tool["name"]: tool for tool in yaml.safe_load(path.read_text(encoding="utf-8"))["tools"]}
    tool = tools["set_render_settings"]
    schema = tool["input_schema"]
    mode, count = schema["properties"]["threads_mode"], schema["properties"]["threads"]
    assert mode["type"] == "string"
    assert mode["enum"] == ["AUTO", "FIXED"]
    assert count["type"] == "integer"
    assert count["minimum"] == 1
    assert "default" not in mode and "default" not in count
    assert tool["source_file"] == "scripts/set_render_settings.py"
    assert tool["affinity"] == "main"
    for name in ("start_render_job", "start_multiview_render_job"):
        assert not {"threads", "threads_mode"} & tools[name]["input_schema"]["properties"].keys()
    try:
        from dcc_mcp_core._core import ToolValidator
    except ImportError:
        pytest.skip("native core ToolValidator unavailable; this is not a Blender-host test")
    validator = ToolValidator.from_schema_json(json.dumps(schema))
    for params in ({}, {"threads": 2}, {"threads_mode": "AUTO"}, {"threads_mode": "FIXED", "threads": 2}):
        assert not validator.validate(json.dumps(params))[1], params
    for params in (
        {"threads": True},
        {"threads": 0},
        {"threads": -1},
        {"threads": "2"},
        {"threads_mode": "fixed"},
        {"threads_mode": False},
        {"threads": None},
        {"threads_mode": None},
    ):
        assert validator.validate(json.dumps(params))[1], params


class NativeLikeRender(SimpleNamespace):
    """Explicit Python double for Blender RNA getter semantics, NOT native QA."""

    @property
    def threads(self):
        if self.override_count:
            return self.override_count
        return self.stored_count if self.stored_mode == "FIXED" else self.host_count

    @threads.setter
    def threads(self, value):
        self.stored_count = value

    @property
    def threads_mode(self):
        return "FIXED" if self.override_count else self.stored_mode

    @threads_mode.setter
    def threads_mode(self, value):
        self.stored_mode = value


def _native_like(bpy, override=0):
    attrs = vars(bpy.context.scene.render).copy()
    del attrs["threads"], attrs["threads_mode"]
    render = NativeLikeRender(**attrs, stored_count=2, stored_mode="AUTO", host_count=8, override_count=override)
    bpy.context.scene.render = render
    return render


def test_auto_readback_uses_host_count_not_hidden_fixed_count(bpy):
    render = _native_like(bpy)
    _assert_readback(bpy, _set(bpy, resolution_x=640), "AUTO", 8)
    _assert_readback(bpy, _set(bpy, threads=4), "FIXED", 4)
    _assert_readback(bpy, _set(bpy, threads_mode="AUTO"), "AUTO", 8)
    assert render.stored_count == 4


@pytest.mark.parametrize("params", [{"threads": 4}, {"threads_mode": "AUTO"}])
def test_process_override_mismatch_reports_actual_state_without_fake_rollback(bpy, params):
    render = _native_like(bpy, override=8)
    render.stored_mode = "FIXED"
    result = _set(bpy, resolution_x=640, **params)
    assert result["success"] is False, result
    assert result["context"]["threads_mode"] == "FIXED"
    assert result["context"]["threads"] == 8
    assert result["context"]["thread_settings_may_have_changed"] is True
    assert render.resolution_x == 1920
    assert render.stored_count == params.get("threads", 2)
    assert render.stored_mode == ("FIXED" if "threads" in params else "AUTO")


@pytest.mark.parametrize("field", ["threads", "threads_mode"])
def test_failed_native_readback_keeps_partial_change_diagnostic(bpy, field):
    class FailingGetter(SimpleNamespace):
        def __getattribute__(self, name):
            if name == field and super().__getattribute__("fail_readback"):
                raise RuntimeError("native getter unavailable")
            return super().__getattribute__(name)

        def __setattr__(self, name, value):
            super().__setattr__(name, value)
            if name == "threads_mode":
                super().__setattr__("fail_readback", True)

    bpy.context.scene.render = FailingGetter(**vars(bpy.context.scene.render), fail_readback=False)
    result = _set(bpy, resolution_x=640, threads=4)
    assert result["success"] is False, result
    assert result["context"]["thread_settings_may_have_changed"] is True
    assert result["context"][field] is None
    assert bpy.context.scene.render.resolution_x == 1920
