"""Unit tests for blender-geometry-nodes skill scripts (bpy mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


def _make_mesh_obj(name="Cube"):
    obj = MagicMock()
    obj.name = name
    obj.type = "MESH"
    obj.modifiers = MagicMock()
    obj.modifiers.__iter__ = MagicMock(return_value=iter([]))
    return obj


class TestAddGeometryNodesModifier:
    def test_adds_modifier_and_node_group(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        bpy.data.objects.get.return_value = obj

        modifier = MagicMock()
        modifier.name = "Geometry Nodes"
        modifier.type = "NODES"
        obj.modifiers.new.return_value = modifier

        group = MagicMock()
        group.name = "Procedural Group"
        bpy.data.node_groups.get.return_value = None
        bpy.data.node_groups.new.return_value = group

        result = load_and_call(
            "blender-geometry-nodes/scripts/add_geometry_nodes_modifier.py",
            bpy,
            object_name="Cube",
            group_name="Procedural Group",
        )

        assert result["success"] is True
        obj.modifiers.new.assert_called_once_with(name="Geometry Nodes", type="NODES")
        bpy.data.node_groups.new.assert_called_once_with("Procedural Group", "GeometryNodeTree")
        assert modifier.node_group is group

    def test_non_mesh_returns_error(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj("Light")
        obj.type = "LIGHT"
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-geometry-nodes/scripts/add_geometry_nodes_modifier.py",
            bpy,
            object_name="Light",
        )

        assert result["success"] is False


class TestListGeometryNodesModifiers:
    def test_lists_only_geometry_nodes_modifiers(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        group = MagicMock()
        group.name = "GeoGroup"

        geo = MagicMock()
        geo.name = "Geometry Nodes"
        geo.type = "NODES"
        geo.node_group = group
        geo.show_viewport = True
        geo.show_render = True

        bevel = MagicMock()
        bevel.name = "Bevel"
        bevel.type = "BEVEL"

        obj.modifiers.__iter__ = MagicMock(return_value=iter([geo, bevel]))
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-geometry-nodes/scripts/list_geometry_nodes_modifiers.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["modifiers"][0]["node_group"] == "GeoGroup"

    def test_missing_object_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None

        result = load_and_call(
            "blender-geometry-nodes/scripts/list_geometry_nodes_modifiers.py",
            bpy,
            object_name="Ghost",
        )

        assert result["success"] is False
