"""Unit tests for blender-lighting skill scripts (bpy mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


def _make_light_obj(name="Light", light_type="POINT"):
    obj = MagicMock()
    obj.name = name
    obj.type = "LIGHT"
    obj.location = [0.0, 0.0, 3.0]
    obj.data = MagicMock()
    obj.data.type = light_type
    obj.data.energy = 1000.0
    obj.data.color = [1.0, 1.0, 1.0]
    return obj


class TestCreateLight:
    def test_create_point_light(self):
        bpy = make_mock_bpy()
        light_data = MagicMock()
        light_data.name = "Point Light"
        bpy.data.lights.new = MagicMock(return_value=light_data)

        obj = _make_light_obj("PointLight")
        bpy.data.objects.new.return_value = obj
        bpy.context.scene.collection.objects.link = MagicMock()

        result = load_and_call("blender-lighting/scripts/create_light.py", bpy, light_type="POINT")
        assert result["success"] is True
        bpy.data.lights.new.assert_called_once()

    def test_create_sun_light(self):
        bpy = make_mock_bpy()
        light_data = MagicMock()
        bpy.data.lights.new = MagicMock(return_value=light_data)
        obj = _make_light_obj("Sun", "SUN")
        bpy.data.objects.new.return_value = obj
        bpy.context.scene.collection.objects.link = MagicMock()

        result = load_and_call("blender-lighting/scripts/create_light.py", bpy, light_type="SUN")
        assert result["success"] is True
        args, kwargs = bpy.data.lights.new.call_args
        assert kwargs.get("type") == "SUN" or "SUN" in args

    def test_invalid_type_returns_error(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-lighting/scripts/create_light.py", bpy, light_type="INVALID")
        assert result["success"] is False

    def test_sets_energy(self):
        bpy = make_mock_bpy()
        light_data = MagicMock()
        bpy.data.lights.new = MagicMock(return_value=light_data)
        obj = _make_light_obj()
        bpy.data.objects.new.return_value = obj
        bpy.context.scene.collection.objects.link = MagicMock()

        load_and_call("blender-lighting/scripts/create_light.py", bpy, energy=5000.0)
        assert light_data.energy == 5000.0


class TestSetLightProperties:
    def test_sets_energy(self):
        bpy = make_mock_bpy()
        obj = _make_light_obj()
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-lighting/scripts/set_light_properties.py",
            bpy,
            name="Light",
            energy=2000.0,
        )
        assert result["success"] is True
        assert obj.data.energy == 2000.0

    def test_object_not_found(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None
        result = load_and_call("blender-lighting/scripts/set_light_properties.py", bpy, name="Ghost")
        assert result["success"] is False

    def test_non_light_returns_error(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.type = "MESH"
        bpy.data.objects.get.return_value = obj
        result = load_and_call("blender-lighting/scripts/set_light_properties.py", bpy, name="Cube")
        assert result["success"] is False


class TestListLights:
    def test_returns_only_lights(self):
        bpy = make_mock_bpy()
        light_obj = _make_light_obj("Sun", "SUN")
        mesh_obj = MagicMock()
        mesh_obj.type = "MESH"
        bpy.data.objects = [light_obj, mesh_obj]

        result = load_and_call("blender-lighting/scripts/list_lights.py", bpy)
        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["lights"][0]["name"] == "Sun"

    def test_empty_scene(self):
        bpy = make_mock_bpy(data_attrs={"objects": []})
        result = load_and_call("blender-lighting/scripts/list_lights.py", bpy)
        assert result["success"] is True
        assert result["context"]["count"] == 0


class TestSetWorldBackground:
    def test_sets_existing_world_color(self):
        bpy = make_mock_bpy()

        result = load_and_call(
            "blender-lighting/scripts/set_world_background.py",
            bpy,
            color=[0.1, 0.2, 0.3],
        )

        assert result["success"] is True
        assert bpy.context.scene.world.color == [0.1, 0.2, 0.3]
        assert result["context"]["color"] == [0.1, 0.2, 0.3, 1.0]

    def test_creates_world_when_missing(self):
        bpy = make_mock_bpy()
        bpy.context.scene.world = None
        new_world = MagicMock()
        bpy.data.worlds.new.return_value = new_world

        result = load_and_call(
            "blender-lighting/scripts/set_world_background.py",
            bpy,
            color=[0.4, 0.5, 0.6, 0.7],
            strength=2.5,
        )

        assert result["success"] is True
        bpy.data.worlds.new.assert_called_once_with(name="World")
        assert bpy.context.scene.world is new_world
        assert new_world.color == [0.4, 0.5, 0.6]
        assert new_world.strength == 2.5

    def test_rejects_invalid_color_length(self):
        bpy = make_mock_bpy()

        result = load_and_call("blender-lighting/scripts/set_world_background.py", bpy, color=[1.0, 0.5])

        assert result["success"] is False
