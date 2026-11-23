"""Tests for reference-driven scene bound validation."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

from tests.conftest import load_and_call, load_skill_script, make_mock_bpy


class _Collection(list):
    def get(self, name):
        for item in self:
            if item.name == name:
                return item
        return None


def _box_object(name, minimum, maximum, location=(0.0, 0.0, 0.0), object_type="MESH"):
    x0, y0, z0 = minimum
    x1, y1, z1 = maximum
    return SimpleNamespace(
        name=name,
        type=object_type,
        location=location,
        bound_box=[
            (x0, y0, z0),
            (x0, y0, z1),
            (x0, y1, z0),
            (x0, y1, z1),
            (x1, y0, z0),
            (x1, y0, z1),
            (x1, y1, z0),
            (x1, y1, z1),
        ],
        hide_viewport=False,
        hide_render=False,
    )


def _make_bpy(*objects):
    bpy = make_mock_bpy()
    bpy.data.objects = _Collection(objects)
    return bpy


def test_validate_scene_bounds_reports_world_space_projection_and_ratio():
    bpy = _make_bpy(_box_object("Body_Main", (0, 0, 0), (4, 1, 2), location=(1, 0, 3)))

    result = load_and_call(
        "blender-validation/scripts/validate_scene_bounds.py",
        bpy,
        object_names=["Body_Main"],
        expected_ratio=2.0,
        ratio_tolerance=0.0001,
    )

    assert result["success"] is True
    assert result["context"]["report"]["passed"] is True
    bounds = result["context"]["bounds"]
    assert bounds["min"] == [1.0, 0.0, 3.0]
    assert bounds["max"] == [5.0, 1.0, 5.0]
    assert bounds["width_height_ratio"] == 2.0


def test_validate_scene_bounds_applies_matrix_world(monkeypatch):
    class _Vector(list):
        pass

    class _Matrix:
        def __matmul__(self, vector):
            return _Vector([vector[0] + 10.0, vector[1] - 2.0, vector[2] + 4.0])

    monkeypatch.setitem(sys.modules, "mathutils", SimpleNamespace(Vector=_Vector))
    obj = _box_object("Hero", (0, 0, 0), (4, 1, 2))
    obj.matrix_world = _Matrix()
    bpy = _make_bpy(obj)

    module = load_skill_script("blender-validation", "validate_scene_bounds")
    with patch.dict(sys.modules, {"bpy": bpy, "mathutils": SimpleNamespace(Vector=_Vector)}):
        result = module.main(object_names=["Hero"])

    assert result["success"] is True
    assert result["context"]["bounds"]["min"] == [10.0, -2.0, 4.0]
    assert result["context"]["bounds"]["max"] == [14.0, -1.0, 6.0]


def test_validate_scene_bounds_reports_ratio_drift_and_prefix_exclusions():
    bpy = _make_bpy(
        _box_object("Weapon_Main", (0, 0, 0), (4, 1, 2)),
        _box_object("Display_Backdrop", (-10, 0, -10), (10, 1, 10)),
    )

    result = load_and_call(
        "blender-validation/scripts/validate_scene_bounds.py",
        bpy,
        name_prefixes=["Weapon_", "Display_"],
        exclude_name_prefixes=["Display_"],
        expected_ratio=1.0,
    )

    assert result["success"] is True
    assert result["context"]["report"]["passed"] is False
    assert result["context"]["report"]["checked_objects"] == ["Weapon_Main"]
    codes = {issue["code"] for issue in result["context"]["report"]["issues"]}
    assert "SCENE_BOUNDS_RATIO_MISMATCH" in codes
