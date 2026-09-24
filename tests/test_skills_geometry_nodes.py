"""Unit tests for blender-geometry-nodes skill scripts (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

GEOMETRY_NODES_DIR = "blender-geometry-nodes"
GEOMETRY_NODES_PATH = "src/dcc_mcp_blender/skills/blender-geometry-nodes/tools.yaml"


class FakeSocket:
    """Blender 4.x style interface socket; direction lives in ``in_out``."""

    def __init__(self, name, socket_type, in_out):
        self.name = name
        self.identifier = name
        self.socket_type = socket_type
        self.in_out = in_out


class FakeLegacySocket:
    """Blender 3.6 style ``NodeSocketInterface``; direction lives in ``is_output``.

    Deliberately has **no** ``in_out`` attribute, matching real Blender 3.6, so a
    production read of ``getattr(socket, \"in_out\", ...)`` cannot silently satisfy
    itself off this fake.
    """

    def __init__(self, name, socket_type, is_output):
        self.name = name
        self.identifier = name
        self.socket_type = socket_type
        self.is_output = is_output


class FakeLinks(list):
    def new(self, from_socket, to_socket):
        link = SimpleNamespace(from_socket=from_socket, to_socket=to_socket)
        self.append(link)
        return link


class FakeNodes(list):
    """Node collection that mirrors the group interface onto new group nodes."""

    def __init__(self, group):
        super().__init__()
        self._group = group

    def new(self, type):  # noqa: A002
        node = SimpleNamespace(
            name=type, type=type, bl_idname=type, inputs={}, outputs={}, label="", location=[0.0, 0.0]
        )
        self.append(node)
        interface = getattr(self._group, "interface", None)
        if interface is not None:
            interface.mirror(node)
        else:
            # Legacy 3.6 collections carry no direction on the socket itself: the
            # collection it lives in is the direction. Infer it from there instead
            # of reading ``socket.in_out``, which real 3.6 sockets do not expose.
            for collection, in_out in (
                (getattr(self._group, "inputs", []), "INPUT"),
                (getattr(self._group, "outputs", []), "OUTPUT"),
            ):
                for socket in collection:
                    if node.bl_idname == "NodeGroupInput" and in_out == "INPUT":
                        node.outputs[socket.name] = FakeSocket(socket.name, socket.socket_type, "OUTPUT")
                    elif node.bl_idname == "NodeGroupOutput" and in_out == "OUTPUT":
                        node.inputs[socket.name] = FakeSocket(socket.name, socket.socket_type, "INPUT")
        return node


class FakeInterface(list):
    """Minimal NodeTreeInterface; sockets mirror onto the group's group nodes."""

    def __init__(self, group):
        super().__init__()
        self._group = group

    @property
    def items_tree(self):
        return self

    def mirror(self, node):
        for socket in self:
            if socket.in_out == "INPUT" and node.bl_idname == "NodeGroupInput":
                node.outputs[socket.name] = FakeSocket(socket.name, socket.socket_type, "OUTPUT")
            elif socket.in_out == "OUTPUT" and node.bl_idname == "NodeGroupOutput":
                node.inputs[socket.name] = FakeSocket(socket.name, socket.socket_type, "INPUT")

    def new_socket(self, name, in_out, socket_type):
        socket = SimpleNamespace(name=name, identifier=name, in_out=in_out, socket_type=socket_type)
        self.append(socket)
        for node in self._group.nodes:
            self.mirror(node)
        return socket


class FakeNodeGroup:
    def __init__(self, name="GeoGroup"):
        self.name = name
        self.type = "GeometryNodeTree"
        self.bl_idname = "GeometryNodeTree"
        self.interface = FakeInterface(self)
        self.nodes = FakeNodes(self)
        self.links = FakeLinks()

    def socket_names(self, in_out):
        return [socket.name for socket in self.interface if socket.in_out == in_out]


class FakeLegacySockets(list):
    """Blender 3.6 style ``node_tree.inputs`` / ``node_tree.outputs`` collection."""

    def __init__(self, group, in_out):
        super().__init__()
        self._group = group
        self._in_out = in_out

    def _mirror(self, socket):
        for node in self._group.nodes:
            if self._in_out == "INPUT" and node.bl_idname == "NodeGroupInput":
                node.outputs[socket.name] = FakeSocket(socket.name, socket.socket_type, "OUTPUT")
            elif self._in_out == "OUTPUT" and node.bl_idname == "NodeGroupOutput":
                node.inputs[socket.name] = FakeSocket(socket.name, socket.socket_type, "INPUT")

    def new(self, socket_type, name):
        socket = FakeLegacySocket(name, socket_type, self._in_out == "OUTPUT")
        self.append(socket)
        self._mirror(socket)
        return socket


class FakeLegacyNodeGroup:
    """Blender 3.6 geometry node tree: no ``interface`` API, legacy socket collections."""

    def __init__(self, name="LegacyGroup"):
        self.name = name
        self.type = "GeometryNodeTree"
        self.bl_idname = "GeometryNodeTree"
        self.interface = None
        self.nodes = FakeNodes(self)
        self.links = FakeLinks()
        self.inputs = FakeLegacySockets(self, "INPUT")
        self.outputs = FakeLegacySockets(self, "OUTPUT")


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


class TestGeometryNodeGroupTemplates:
    """A created group must expose interface sockets agents can wire against."""

    def _create(self, bpy, name, **kwargs):
        return load_and_call(f"{GEOMETRY_NODES_DIR}/scripts/create_geometry_node_group.py", bpy, name=name, **kwargs)

    def test_default_template_creates_wired_geometry_pass_through(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        created = self._create(bpy, "ScatterGroup", template="default")

        assert created["success"] is True
        group = bpy.data.node_groups.get("ScatterGroup")
        assert group.socket_names("INPUT") == ["Geometry"]
        assert group.socket_names("OUTPUT") == ["Geometry"]
        assert created["context"]["template"] == "pass_through"
        assert created["context"]["input_count"] == 1
        assert created["context"]["output_count"] == 1
        assert [record["name"] for record in created["context"]["interface_sockets"]] == ["Geometry", "Geometry"]

    def test_pass_through_links_group_input_to_group_output(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        self._create(bpy, "ScatterGroup", template="pass_through")

        group = bpy.data.node_groups.get("ScatterGroup")
        assert len(group.nodes) == 2
        assert len(group.links) == 1
        link = group.links[0]
        assert link.from_socket.name == "Geometry"
        assert link.to_socket.name == "Geometry"

    def test_pass_through_is_idempotent(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        self._create(bpy, "ScatterGroup", template="pass_through")
        second = self._create(bpy, "ScatterGroup", template="pass_through")

        group = bpy.data.node_groups.get("ScatterGroup")
        assert second["context"]["created"] is False
        assert group.socket_names("INPUT") == ["Geometry"]
        assert len(group.nodes) == 2
        assert len(group.links) == 1

    def test_omitted_template_defaults_to_pass_through(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        created = self._create(bpy, "ScatterGroup")

        group = bpy.data.node_groups.get("ScatterGroup")
        assert created["context"]["template"] == "pass_through"
        assert group.socket_names("INPUT") == ["Geometry"]
        assert len(group.links) == 1

    def test_empty_template_leaves_group_bare_but_reported(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        created = self._create(bpy, "BareGroup", template="empty")

        group = bpy.data.node_groups.get("BareGroup")
        assert created["success"] is True
        assert created["context"]["interface_sockets"] == []
        assert created["context"]["input_count"] == 0
        assert group.nodes == []
        assert group.links == []

    def test_empty_group_is_repaired_by_a_later_pass_through_call(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        self._create(bpy, "BareGroup", template="empty")
        repaired = self._create(bpy, "BareGroup", template="pass_through")

        group = bpy.data.node_groups.get("BareGroup")
        assert repaired["context"]["template_applied"] is True
        assert group.socket_names("INPUT") == ["Geometry"]
        assert len(group.links) == 1

    def test_authored_graph_is_not_rewritten_by_get_or_create(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        self._create(bpy, "AuthoredGroup", template="empty")
        group = bpy.data.node_groups.get("AuthoredGroup")
        custom = group.nodes.new("GeometryNodeSubdivide")

        loaded = self._create(bpy, "AuthoredGroup", template="pass_through")

        assert loaded["context"]["template_applied"] is False
        assert group.socket_names("INPUT") == []
        assert group.nodes == [custom]
        assert group.links == []

    def test_legacy_3_6_fake_sockets_carry_is_output_and_no_in_out(self):
        """Keep the legacy fake faithful to Blender 3.6 ``NodeSocketInterface``.

        Blender 3.6 exposes ``is_output`` and has **no** ``in_out``. If the fake
        grew an ``in_out``, ``_add_group_socket`` could go back to reading
        ``getattr(socket, \"in_out\", in_out)`` and this file would still pass,
        so the legacy dedupe regression would go unnoticed until E2E.
        """
        legacy = FakeLegacyNodeGroup("LegacyGroup")
        legacy.inputs.new("NodeSocketGeometry", "Geometry")
        legacy.outputs.new("NodeSocketGeometry", "Geometry")

        for socket in (*legacy.inputs, *legacy.outputs):
            assert not hasattr(socket, "in_out")
        assert legacy.inputs[0].is_output is False
        assert legacy.outputs[0].is_output is True

    def test_pass_through_works_on_legacy_3_6_style_trees(self):
        bpy = make_mock_bpy()
        groups = FakeNodeGroups()
        legacy = FakeLegacyNodeGroup("LegacyGroup")
        groups.append(legacy)
        bpy.data.node_groups = groups

        created = self._create(bpy, "LegacyGroup", template="pass_through")

        assert created["success"] is True
        assert [socket.name for socket in legacy.inputs] == ["Geometry"]
        assert [socket.name for socket in legacy.outputs] == ["Geometry"]
        assert created["context"]["input_count"] == 1
        assert created["context"]["output_count"] == 1
        assert len(legacy.links) == 1
        assert legacy.links[0].from_socket.name == "Geometry"
        assert legacy.links[0].to_socket.name == "Geometry"

    def test_unknown_template_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        created = self._create(bpy, "ScatterGroup", template="scatter")

        assert created["success"] is False
        assert bpy.data.node_groups.get("ScatterGroup") is None


class TestAddGeometryNodesModifierTemplates:
    def test_created_group_is_wired_and_reported(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        bpy.data.objects.get.return_value = obj
        bpy.data.node_groups = FakeNodeGroups()

        result = load_and_call(
            "blender-geometry-nodes/scripts/add_geometry_nodes_modifier.py",
            bpy,
            object_name="Cube",
            group_name="Procedural Group",
        )

        assert result["success"] is True
        group = bpy.data.node_groups.get("Procedural Group")
        assert group.socket_names("INPUT") == ["Geometry"]
        assert group.socket_names("OUTPUT") == ["Geometry"]
        assert len(group.links) == 1
        assert result["context"]["group_created"] is True
        assert result["context"]["group_template"] == "pass_through"

    def test_empty_template_still_available(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        bpy.data.objects.get.return_value = obj
        bpy.data.node_groups = FakeNodeGroups()

        result = load_and_call(
            "blender-geometry-nodes/scripts/add_geometry_nodes_modifier.py",
            bpy,
            object_name="Cube",
            group_name="Bare Group",
            template="empty",
        )

        group = bpy.data.node_groups.get("Bare Group")
        assert result["success"] is True
        assert result["context"]["group_template"] == "empty"
        assert group.socket_names("INPUT") == []
