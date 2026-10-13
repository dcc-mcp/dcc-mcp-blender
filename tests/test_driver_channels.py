"""Driver requests select exactly one channel and preflight before mutation."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import yaml

from dcc_mcp_blender._rigging_ops import set_driver
from tests.test_skills_rigging_pose_animation_ops import RIGGING_DIR, FakeDriver


def object_stub():
    obj = SimpleNamespace(name="Probe", animation_data=None)
    obj.path_resolve = Mock(
        side_effect=lambda path: {"rotation_euler": [0.0, 0.0, 0.0], "empty_display_size": 1.0, '["speed"]': 2.0}[path]
    )
    obj.driver_add = Mock(return_value=SimpleNamespace(driver=FakeDriver()))
    return obj


def invoke(obj, **kwargs):
    bpy = SimpleNamespace(data=SimpleNamespace(objects={obj.name: obj}))
    with patch.dict("sys.modules", {"bpy": bpy}):
        return set_driver(obj.name, expression="frame / 10", **kwargs)


def test_vector_selects_only_z():
    obj = object_stub()
    result = invoke(obj, data_path="rotation_euler", array_index=2)
    assert result["success"]
    assert result["context"]["array_index"] == 2
    obj.driver_add.assert_called_once_with("rotation_euler", 2)


@pytest.mark.parametrize("path", ["empty_display_size", '["speed"]'])
def test_scalar_omits_index(path):
    obj = object_stub()
    assert invoke(obj, data_path=path)["success"]
    obj.driver_add.assert_called_once_with(path)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data_path": "rotation_euler"},
        *[{"data_path": "rotation_euler", "array_index": i} for i in [-1, 3, True, 1.5, "2"]],
        {"data_path": "rotation_euler.z"},
        {"data_path": "rotation_euler[2]"},
        {"data_path": "empty_display_size", "array_index": 0},
        {"data_path": "missing"},
        {
            "data_path": "empty_display_size",
            "variables": [{"name": "valid", "target_data_path": '["speed"]'}, {"target_object": "missing"}],
        },
        {"data_path": "empty_display_size", "variables": [{"type": "LOC_DIFF"}]},
        {"data_path": "empty_display_size", "variables": [{"type": "TRANSFORMS", "transform_type": "bad"}]},
        {"data_path": "empty_display_size", "variables": [{"target_data_path": "rotation_euler"}]},
        {"data_path": "empty_display_size", "variables": [None]},
    ],
)
def test_invalid_requests_do_not_add_driver(kwargs):
    obj = object_stub()
    assert not invoke(obj, **kwargs)["success"]
    obj.driver_add.assert_not_called()


def test_schema_exposes_index_and_no_component_example():
    doc = yaml.safe_load((RIGGING_DIR / "tools.yaml").read_text())
    tool = next(t for t in doc["tools"] if t["name"] == "set_driver")
    props = tool["input_schema"]["properties"]
    assert props["array_index"]["type"] == "integer"
    assert props["array_index"]["minimum"] == 0
    assert "location.x" not in props["data_path"]["description"]


@pytest.mark.parametrize(
    "name",
    ["_speed", "K", "for", "a" * 64, "é" * 32],
)
def test_invalid_variable_names_do_not_mutate_driver(name):
    obj = object_stub()
    assert not invoke(obj, data_path="empty_display_size", variables=[{"name": name, "target_data_path": '["speed"]'}])[
        "success"
    ]
    obj.driver_add.assert_not_called()


@pytest.mark.parametrize("expression", ["1" + " " * 253 + "+2", "1 # " + "é" * 126])
def test_expression_byte_overflow_does_not_mutate_driver(expression):
    obj = object_stub()
    bpy = SimpleNamespace(data=SimpleNamespace(objects={obj.name: obj}))
    with patch.dict("sys.modules", {"bpy": bpy}):
        assert not set_driver(obj.name, "empty_display_size", expression)["success"]
    obj.driver_add.assert_not_called()


@pytest.mark.parametrize("expression", ["  frame / 10", "\tframe / 10", "1" + " " * 252 + "+2", "1 # " + "é" * 125])
def test_supported_expressions_are_stored_unchanged(expression):
    obj = object_stub()
    bpy = SimpleNamespace(data=SimpleNamespace(objects={obj.name: obj}))
    with patch.dict("sys.modules", {"bpy": bpy}):
        assert set_driver(obj.name, "empty_display_size", expression)["success"]
    assert obj.driver_add.return_value.driver.expression == expression
