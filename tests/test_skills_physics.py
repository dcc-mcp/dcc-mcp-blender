"""Unit tests for blender-physics skill scripts (bpy mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


def _make_obj(name="Cube"):
    obj = MagicMock()
    obj.name = name
    obj.type = "MESH"
    obj.rigid_body = None
    return obj


class TestAddRigidBody:
    def test_adds_rigid_body_and_applies_properties(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        rigid_body = MagicMock()
        rigid_body.type = "ACTIVE"
        rigid_body.mass = 1.0
        rigid_body.collision_shape = "CONVEX_HULL"
        bpy.data.objects.get.return_value = obj

        def _add_body(type="ACTIVE"):
            obj.rigid_body = rigid_body
            rigid_body.type = type

        bpy.ops.rigidbody.object_add.side_effect = _add_body

        result = load_and_call(
            "blender-physics/scripts/add_rigid_body.py",
            bpy,
            object_name="Cube",
            body_type="PASSIVE",
            mass="2.5",
            collision_shape="BOX",
        )

        assert result["success"] is True
        bpy.ops.rigidbody.object_add.assert_called_once_with(type="PASSIVE")
        assert rigid_body.mass == 2.5
        assert rigid_body.collision_shape == "BOX"

    def test_invalid_body_type_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = _make_obj()

        result = load_and_call(
            "blender-physics/scripts/add_rigid_body.py",
            bpy,
            object_name="Cube",
            body_type="FLYING",
        )

        assert result["success"] is False


class TestSetRigidBodyProperties:
    def test_updates_existing_rigid_body(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        obj.rigid_body = MagicMock()
        obj.rigid_body.mass = 1.0
        obj.rigid_body.friction = 0.5
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-physics/scripts/set_rigid_body_properties.py",
            bpy,
            object_name="Cube",
            mass="3.0",
            friction="0.2",
        )

        assert result["success"] is True
        assert obj.rigid_body.mass == 3.0
        assert obj.rigid_body.friction == 0.2
        assert result["context"]["applied"]["mass"] == 3.0

    def test_missing_rigid_body_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = _make_obj()

        result = load_and_call(
            "blender-physics/scripts/set_rigid_body_properties.py",
            bpy,
            object_name="Cube",
            mass=3.0,
        )

        assert result["success"] is False


class TestRemoveRigidBody:
    def test_removes_existing_rigid_body(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        obj.rigid_body = MagicMock()
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-physics/scripts/remove_rigid_body.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is True
        bpy.ops.rigidbody.object_remove.assert_called_once_with()

    def test_missing_rigid_body_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = _make_obj()

        result = load_and_call(
            "blender-physics/scripts/remove_rigid_body.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is False
