"""Unit tests for blender-objects skill scripts (bpy mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


def _make_obj(name="Cube", obj_type="MESH", loc=None):
    obj = MagicMock()
    obj.name = name
    obj.type = obj_type
    obj.location = loc or [0.0, 0.0, 0.0]
    obj.rotation_euler = [0.0, 0.0, 0.0]
    obj.scale = [1.0, 1.0, 1.0]
    obj.hide_viewport = False
    obj.hide_render = False
    obj.parent = None
    obj.children = []
    obj.users_collection = []
    obj.material_slots = []
    obj.data = MagicMock()
    return obj


class TestCreateObject:
    def test_create_cube(self):
        bpy = make_mock_bpy()
        obj = _make_obj("Cube")
        bpy.context.active_object = obj

        result = load_and_call("blender-objects/scripts/create_object.py", bpy, object_type="cube")
        assert result["success"] is True
        bpy.ops.mesh.primitive_cube_add.assert_called_once()

    def test_create_sphere(self):
        bpy = make_mock_bpy()
        obj = _make_obj("Sphere")
        bpy.context.active_object = obj

        result = load_and_call("blender-objects/scripts/create_object.py", bpy, object_type="sphere")
        assert result["success"] is True
        bpy.ops.mesh.primitive_uv_sphere_add.assert_called_once()

    def test_create_with_name(self):
        bpy = make_mock_bpy()
        obj = _make_obj("MyCube")
        bpy.context.active_object = obj

        result = load_and_call("blender-objects/scripts/create_object.py", bpy, object_type="cube", name="MyCube")
        assert result["success"] is True

    def test_create_uses_context_object_fallback(self):
        bpy = make_mock_bpy()
        obj = _make_obj("FallbackCube")
        bpy.context.active_object = None
        bpy.context.object = obj

        result = load_and_call("blender-objects/scripts/create_object.py", bpy, object_type="cube", name="FallbackCube")

        assert result["success"] is True
        assert result["context"]["object_name"] == "FallbackCube"

    def test_invalid_type_returns_error(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-objects/scripts/create_object.py", bpy, object_type="invalid_type")
        assert result["success"] is False
        assert "invalid_type" in result["message"].lower()

    def test_create_plane(self):
        bpy = make_mock_bpy()
        obj = _make_obj("Plane")
        bpy.context.active_object = obj
        result = load_and_call("blender-objects/scripts/create_object.py", bpy, object_type="plane")
        assert result["success"] is True
        bpy.ops.mesh.primitive_plane_add.assert_called_once()

    def test_create_empty(self):
        bpy = make_mock_bpy()
        obj = _make_obj("Empty", "EMPTY")
        bpy.context.active_object = obj
        result = load_and_call("blender-objects/scripts/create_object.py", bpy, object_type="empty")
        assert result["success"] is True
        bpy.ops.object.empty_add.assert_called_once()


class TestDuplicateObject:
    def test_duplicate_uses_context_object_fallback(self):
        bpy = make_mock_bpy()
        source = _make_obj("Cube")
        duplicate = _make_obj("Cube.001", loc=[1.0, 2.0, 3.0])
        bpy.data.objects.get.return_value = source
        bpy.context.active_object = None
        bpy.context.object = duplicate

        result = load_and_call(
            "blender-objects/scripts/duplicate_object.py",
            bpy,
            name="Cube",
            new_name="Cube Copy",
        )

        assert result["success"] is True
        assert duplicate.name == "Cube Copy"
        assert result["context"]["new_name"] == "Cube Copy"


class TestDeleteObject:
    def test_delete_existing(self):
        bpy = make_mock_bpy()
        obj = _make_obj("Cube")
        bpy.data.objects.get.return_value = obj

        result = load_and_call("blender-objects/scripts/delete_object.py", bpy, name="Cube")
        assert result["success"] is True
        bpy.data.objects.remove.assert_called_once_with(obj, do_unlink=True)

    def test_delete_nonexistent_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None

        result = load_and_call("blender-objects/scripts/delete_object.py", bpy, name="Ghost")
        assert result["success"] is False
        assert "Ghost" in result["message"]


class TestMoveObject:
    def test_move_sets_location(self):
        bpy = make_mock_bpy()
        obj = _make_obj("Cube")
        bpy.data.objects.get.return_value = obj

        result = load_and_call("blender-objects/scripts/move_object.py", bpy, name="Cube", location=[1.0, 2.0, 3.0])
        assert result["success"] is True
        assert obj.location == [1.0, 2.0, 3.0]

    def test_move_nonexistent_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None

        result = load_and_call("blender-objects/scripts/move_object.py", bpy, name="Ghost", location=[0, 0, 0])
        assert result["success"] is False


class TestRotateObject:
    def test_rotate_converts_degrees_to_radians(self):
        import math

        bpy = make_mock_bpy()
        obj = _make_obj("Cube")
        obj.rotation_euler = [0.0, 0.0, 0.0]
        bpy.data.objects.get.return_value = obj

        result = load_and_call("blender-objects/scripts/rotate_object.py", bpy, name="Cube", rotation=[90.0, 0.0, 0.0])
        assert result["success"] is True
        # Check that radians were applied
        assert abs(obj.rotation_euler[0] - math.radians(90)) < 1e-6

    def test_rotate_nonexistent_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None
        result = load_and_call("blender-objects/scripts/rotate_object.py", bpy, name="Ghost", rotation=[0, 0, 0])
        assert result["success"] is False


class TestScaleObject:
    def test_uniform_scale(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        obj.scale = [1.0, 1.0, 1.0]
        bpy.data.objects.get.return_value = obj

        result = load_and_call("blender-objects/scripts/scale_object.py", bpy, name="Cube", scale=2.0)
        assert result["success"] is True
        assert obj.scale == [2.0, 2.0, 2.0]

    def test_non_uniform_scale(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        bpy.data.objects.get.return_value = obj

        result = load_and_call("blender-objects/scripts/scale_object.py", bpy, name="Cube", scale=[1.0, 2.0, 3.0])
        assert result["success"] is True
        assert obj.scale == [1.0, 2.0, 3.0]

    def test_scale_nonexistent_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None
        result = load_and_call("blender-objects/scripts/scale_object.py", bpy, name="Ghost", scale=1.0)
        assert result["success"] is False


class TestGetObjectInfo:
    def test_returns_mesh_details(self):
        bpy = make_mock_bpy()
        obj = _make_obj("Cube", "MESH")
        obj.data.vertices = [MagicMock()] * 8
        obj.data.edges = [MagicMock()] * 12
        obj.data.polygons = [MagicMock()] * 6
        obj.data.name = "Cube"
        obj.material_slots = []
        bpy.data.objects.get.return_value = obj

        result = load_and_call("blender-objects/scripts/get_object_info.py", bpy, name="Cube")
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["vertex_count"] == 8
        assert ctx["face_count"] == 6

    def test_returns_relationships_and_material_slots(self):
        bpy = make_mock_bpy()
        obj = _make_obj("Cube", "MESH")
        obj.parent = MagicMock()
        obj.parent.name = "Parent"
        child = MagicMock()
        child.name = "Child"
        obj.children = [child]
        collection = MagicMock()
        collection.name = "Collection"
        obj.users_collection = [collection]
        mat = MagicMock()
        mat.name = "Red"
        slot_with_mat = MagicMock()
        slot_with_mat.material = mat
        empty_slot = MagicMock()
        empty_slot.material = None
        obj.material_slots = [slot_with_mat, empty_slot]
        obj.data.vertices = []
        obj.data.edges = []
        obj.data.polygons = []
        bpy.data.objects.get.return_value = obj

        result = load_and_call("blender-objects/scripts/get_object_info.py", bpy, name="Cube")

        assert result["success"] is True
        ctx = result["context"]
        assert ctx["parent"] == "Parent"
        assert ctx["children"] == ["Child"]
        assert ctx["collections"] == ["Collection"]
        assert ctx["material_slots"] == ["Red", None]

    def test_nonexistent_object_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None
        result = load_and_call("blender-objects/scripts/get_object_info.py", bpy, name="Ghost")
        assert result["success"] is False
