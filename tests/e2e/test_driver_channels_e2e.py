"""Native driver channel isolation and preflight regression tests."""

import pytest

bpy = pytest.importorskip("bpy")
pytestmark = pytest.mark.e2e

from dcc_mcp_blender._rigging_ops import set_driver  # noqa: E402


@pytest.fixture
def obj():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = bpy.data.objects.new("DriverProbe", None)
    bpy.context.collection.objects.link(obj)
    return obj


def snapshot(obj):
    return [
        (
            f.data_path,
            f.array_index,
            f.driver.type,
            f.driver.expression,
            [
                (v.name, v.type, [(t.id, t.data_path, t.transform_type, t.transform_space) for t in v.targets])
                for v in f.driver.variables
            ],
        )
        for f in obj.animation_data.drivers
    ]


def test_native_z_only_and_preserved_xy(obj):
    result = set_driver(obj.name, "rotation_euler", "frame / 10", array_index=2)
    assert result["success"], result
    assert [(f.data_path, f.array_index) for f in obj.animation_data.drivers] == [("rotation_euler", 2)]
    bpy.context.scene.frame_set(10)
    assert tuple(obj.rotation_euler) == pytest.approx((0, 0, 1))
    obj.driver_add("rotation_euler", 0).driver.expression = "0.25"
    obj.driver_add("rotation_euler", 1).driver.expression = "0.5"
    before = snapshot(obj)
    assert set_driver(obj.name, "rotation_euler", "frame / 20", array_index=2)["success"]
    assert snapshot(obj)[1:] == before[1:]
    bpy.context.scene.frame_set(20)
    assert tuple(obj.rotation_euler) == pytest.approx((0.25, 0.5, 1))


def test_native_scalar_and_variable(obj):
    obj["speed"] = 2.0
    result = set_driver(
        obj.name, "empty_display_size", "speed * 2", variables=[{"name": "speed", "target_data_path": '["speed"]'}]
    )
    assert result["success"], result
    bpy.context.scene.frame_set(10)
    assert obj.empty_display_size == pytest.approx(4)
    assert set_driver(obj.name, '["speed"]', "3")["success"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data_path": "rotation_euler"},
        {"data_path": "rotation_euler", "array_index": -1},
        {"data_path": "rotation_euler", "array_index": 3},
        {"data_path": "rotation_euler", "array_index": True},
        {"data_path": "rotation_euler.z"},
        {"data_path": "rotation_euler[2]"},
        {"data_path": "empty_display_size", "array_index": 0},
        {"data_path": "missing"},
        {"data_path": "empty_display_size", "expression": "("},
        {
            "data_path": "empty_display_size",
            "variables": [
                {"name": "ok", "target_data_path": "empty_display_size"},
                {"name": "bad", "target_object": "missing", "target_data_path": "empty_display_size"},
            ],
        },
        {"data_path": "empty_display_size", "variables": [{"type": "INVALID"}]},
        {"data_path": "empty_display_size", "variables": [{"target_data_path": "missing"}]},
        {"data_path": "empty_display_size", "expression": "1" + " " * 253 + "+2"},
        {"data_path": "empty_display_size", "expression": "1 # " + "é" * 126},
        *[
            {"data_path": "empty_display_size", "variables": [{"name": name, "target_data_path": "empty_display_size"}]}
            for name in ["_speed", "K", "for", "a" * 64, "é" * 32]
        ],
    ],
)
def test_native_error_preserves_existing_driver(obj, kwargs):
    obj.driver_add("empty_display_size").driver.expression = "7"
    before = snapshot(obj)
    args = {"expression": "frame / 10", **kwargs}
    result = set_driver(obj.name, **args)
    assert not result["success"], result
    assert snapshot(obj) == before


@pytest.mark.parametrize("expression", ["  1 + 2", "\t1 + 2", "1" + " " * 252 + "+2", "3 # " + "é" * 125])
def test_native_expression_boundaries(obj, expression):
    assert set_driver(obj.name, "empty_display_size", expression)["success"]
    assert obj.animation_data.drivers[0].driver.expression == expression
    bpy.context.scene.frame_set(10)
    assert obj.empty_display_size == pytest.approx(3)


@pytest.mark.parametrize("name", ["speed", "a" * 63, "é" * 31])
def test_native_variable_name_boundaries(obj, name):
    obj["speed"] = 2.0
    result = set_driver(
        obj.name, "empty_display_size", name + " * 2", variables=[{"name": name, "target_data_path": '["speed"]'}]
    )
    assert result["success"], result
    variable = obj.animation_data.drivers[0].driver.variables[0]
    assert variable.name == name
    assert variable.is_name_valid
    bpy.context.scene.frame_set(10)
    assert obj.empty_display_size == pytest.approx(4)


def test_native_duplicate_variable_preserves_targets_and_expression(obj):
    obj["speed"] = 2.0
    variables = [{"name": "speed", "target_data_path": '["speed"]'}]
    assert set_driver(obj.name, "empty_display_size", "speed * 2", variables)["success"]
    before = snapshot(obj)
    result = set_driver(obj.name, "empty_display_size", "speed * 3", variables)
    assert not result["success"], result
    assert snapshot(obj) == before


def test_native_transform_variable_and_numeric_custom_array(obj):
    target = bpy.data.objects.new("Target", None)
    bpy.context.collection.objects.link(target)
    target.location.z = 3
    obj["array"] = [1.0, 2.0, 3.0]
    result = set_driver(
        obj.name,
        '["array"]',
        "height * 2",
        [{"name": "height", "type": "TRANSFORMS", "target_object": target.name, "transform_type": "LOC_Z"}],
        array_index=1,
    )
    assert result["success"], result
    bpy.context.scene.frame_set(10)
    assert tuple(obj["array"]) == pytest.approx((1, 6, 3))
    assert [(f.data_path, f.array_index) for f in obj.animation_data.drivers] == [('["array"]', 1)]
