"""Unit tests for blender-geometry-nodes skill scripts (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

GEOMETRY_NODES_DIR = "blender-geometry-nodes"
GEOMETRY_NODES_PATH = "src/dcc_mcp_blender/skills/blender-geometry-nodes/tools.yaml"


class FakeNodes(list):
    def new(self, type):  # noqa: A002
        node = SimpleNamespace(
            name=type, type=type, bl_idname=type, inputs={}, outputs={}, label="", location=[0.0, 0.0]
        )
        self.append(node)
        return node


class FakeLinks(list):
    pass


class FakeInterface(list):
    def new_socket(self, name, in_out, socket_type):
        socket = SimpleNamespace(name=name, identifier=name, in_out=in_out, socket_type=socket_type)
        self.append(socket)
        return socket


class FakeNodeGroup:
    def __init__(self, name="GeoGroup"):
        self.name = name
        self.type = "GeometryNodeTree"
        self.bl_idname = "GeometryNodeTree"
        self.nodes = FakeNodes()
        self.links = FakeLinks()
        self.interface = SimpleNamespace(items_tree=FakeInterface())


class FakeNodeGroups(list):
    def get(self, name):
        return next((group for group in self if group.name == name), None)

    def new(self, name, tree_type):
        group = FakeNodeGroup(name)
        group.type = tree_type
        self.append(group)
        return group


class FakeModifier(dict):
    def __init__(self, name="Geometry Nodes", node_group=None):
        super().__init__()
        self.name = name
        self.type = "NODES"
        self.node_group = node_group
        self.show_viewport = True
        self.show_render = True


class FakeModifiers(list):
    def new(self, name, type):  # noqa: A002
        modifier = FakeModifier(name)
        modifier.type = type
        self.append(modifier)
        return modifier


def _make_mesh_obj(name="Cube"):
    obj = MagicMock()
    obj.name = name
    obj.type = "MESH"
    obj.modifiers = FakeModifiers()
    return obj


def test_geometry_nodes_tools_yaml_declares_modern_contracts():
    doc = yaml.safe_load(Path(GEOMETRY_NODES_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {
        "create_geometry_node_group",
        "assign_geometry_node_group",
        "set_geometry_node_modifier_input",
        "evaluate_geometry_nodes_info",
    }.issubset(tools)
    for tool in tools.values():
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert tool["input_schema"]["type"] == "object"
        assert tool["output_schema"]["properties"]["success"]["type"] == "boolean"
        assert "annotations" in tool


class TestAddGeometryNodesModifier:
    def test_adds_modifier_and_node_group(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        bpy.data.objects.get.return_value = obj

        groups = FakeNodeGroups()
        bpy.data.node_groups = groups

        result = load_and_call(
            "blender-geometry-nodes/scripts/add_geometry_nodes_modifier.py",
            bpy,
            object_name="Cube",
            group_name="Procedural Group",
        )

        assert result["success"] is True
        assert obj.modifiers[0].name == "Geometry Nodes"
        assert obj.modifiers[0].node_group is groups[0]

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
        group = FakeNodeGroup("GeoGroup")

        geo = FakeModifier("Geometry Nodes", group)

        bevel = MagicMock()
        bevel.name = "Bevel"
        bevel.type = "BEVEL"

        obj.modifiers.extend([geo, bevel])
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


class TestGeometryNodeGraphTools:
    def test_create_assign_set_and_evaluate_modifier_input(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        bpy.data.objects.get.return_value = obj
        bpy.data.node_groups = FakeNodeGroups()

        created = load_and_call(
            f"{GEOMETRY_NODES_DIR}/scripts/create_geometry_node_group.py",
            bpy,
            name="ScatterGroup",
            template="pass_through",
        )
        assert created["success"] is True
        group = bpy.data.node_groups.get("ScatterGroup")
        group.interface.items_tree.new_socket("Scale", "INPUT", "NodeSocketFloat")

        second_create = load_and_call(
            f"{GEOMETRY_NODES_DIR}/scripts/create_geometry_node_group.py",
            bpy,
            name="ScatterGroup",
            template="pass_through",
        )
        assert second_create["success"] is True
        assert len(group.nodes) == 2
        assert [(socket.name, socket.in_out) for socket in group.interface.items_tree].count(("Geometry", "INPUT")) == 1
        assert [(socket.name, socket.in_out) for socket in group.interface.items_tree].count(
            ("Geometry", "OUTPUT")
        ) == 1

        assigned = load_and_call(
            f"{GEOMETRY_NODES_DIR}/scripts/assign_geometry_node_group.py",
            bpy,
            object_name="Cube",
            group_name="ScatterGroup",
            modifier_name="Scatter",
        )
        assert assigned["success"] is True
        assert obj.modifiers[0].node_group is group

        updated = load_and_call(
            f"{GEOMETRY_NODES_DIR}/scripts/set_geometry_node_modifier_input.py",
            bpy,
            object_name="Cube",
            modifier_name="Scatter",
            input_name="Scale",
            value=2.5,
        )
        assert updated["success"] is True
        assert obj.modifiers[0]["Scale"] == 2.5

        info = load_and_call(
            f"{GEOMETRY_NODES_DIR}/scripts/evaluate_geometry_nodes_info.py",
            bpy,
            object_name="Cube",
            modifier_name="Scatter",
        )
        assert info["success"] is True
        assert {
            "name": "Scale",
            "identifier": "Scale",
            "value": 2.5,
            "in_out": "INPUT",
            "type": "NodeSocketFloat",
        } in info["context"]["inputs"]

    def test_missing_group_and_non_mesh_return_errors(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj("Light")
        obj.type = "LIGHT"
        bpy.data.objects.get.return_value = obj
        bpy.data.node_groups = FakeNodeGroups()

        assigned = load_and_call(
            f"{GEOMETRY_NODES_DIR}/scripts/assign_geometry_node_group.py",
            bpy,
            object_name="Light",
            group_name="Missing",
        )
        assert assigned["success"] is False
