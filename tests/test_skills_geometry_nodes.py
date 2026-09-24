"""Unit tests for blender-geometry-nodes skill scripts (bpy mocked)."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

GEOMETRY_NODES_DIR = "blender-geometry-nodes"
GEOMETRY_NODES_PATH = "src/dcc_mcp_blender/skills/blender-geometry-nodes/tools.yaml"


def _socket_type_of(socket):
    """Read a socket type through the same fallback production uses."""
    return getattr(socket, "socket_type", None) or getattr(socket, "type", None)


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


class FakeBrokenLinks(FakeLinks):
    """Links collection that refuses to create links, like incompatible Blender sockets."""

    def new(self, from_socket, to_socket):
        raise TypeError(f"Cannot link {from_socket.socket_type} to {to_socket.socket_type}")


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

    def sockets(self):
        """Only real sockets carry ``in_out``; Blender 4.x panels are layout items."""
        return [item for item in self if getattr(item, "item_type", "SOCKET") == "SOCKET"]

    def mirror(self, node):
        for socket in self.sockets():
            if socket.in_out == "INPUT" and node.bl_idname == "NodeGroupInput":
                node.outputs[socket.name] = FakeSocket(socket.name, _socket_type_of(socket), "OUTPUT")
            elif socket.in_out == "OUTPUT" and node.bl_idname == "NodeGroupOutput":
                node.inputs[socket.name] = FakeSocket(socket.name, _socket_type_of(socket), "INPUT")

    def new_socket(self, name, in_out, socket_type):
        socket = SimpleNamespace(name=name, identifier=name, in_out=in_out, socket_type=socket_type, item_type="SOCKET")
        self.append(socket)
        for node in self._group.nodes:
            self.mirror(node)
        return socket

    def new_panel(self, name):
        """Append a Blender 4.x ``NodeTreeInterfacePanel``: named, but not a socket."""
        panel = SimpleNamespace(name=name, item_type="PANEL")
        self.append(panel)
        return panel


class FakeNodeGroup:
    def __init__(self, name="GeoGroup"):
        self.name = name
        self.type = "GeometryNodeTree"
        self.bl_idname = "GeometryNodeTree"
        self.interface = FakeInterface(self)
        self.nodes = FakeNodes(self)
        self.links = FakeLinks()

    def socket_names(self, in_out):
        return [socket.name for socket in self.interface.sockets() if socket.in_out == in_out]


class FakeLegacySockets(list):
    """Blender 3.6 style ``node_tree.inputs`` / ``node_tree.outputs`` collection."""

    def __init__(self, group, in_out):
        super().__init__()
        self._group = group
        self._in_out = in_out

    def _mirror(self, socket):
        socket_type = _socket_type_of(socket)
        for node in self._group.nodes:
            if self._in_out == "INPUT" and node.bl_idname == "NodeGroupInput":
                node.outputs[socket.name] = FakeSocket(socket.name, socket_type, "OUTPUT")
            elif self._in_out == "OUTPUT" and node.bl_idname == "NodeGroupOutput":
                node.inputs[socket.name] = FakeSocket(socket.name, socket_type, "INPUT")

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


def _documented_return_fields(skill_md: str, tool_name: str) -> set:
    """Extract the return-contract field names SKILL.md documents for one tool.

    Drift in either direction fails: a field the tool returns but the doc drops,
    or a field the doc advertises but the tool never sets.
    """
    lines = skill_md.splitlines()
    start = lines.index("## Return contract")
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    section = lines[start:end]

    fields = set()
    active = False
    for line in section:
        marker = re.match(r"^`([a-z_]+)`", line)
        if marker:
            active = marker.group(1) == tool_name
            continue
        if not active:
            continue
        bullet = re.match(r"^- `([a-z_]+)`", line)
        if bullet:
            fields.add(bullet.group(1))
    return fields


class TestGeometryNodesReturnContract:
    """SKILL.md must describe the context each tool really returns."""

    CREATE_FIELDS = {
        "group_name",
        "template",
        "created",
        "template_applied",
        "node_count",
        "link_count",
        "interface_sockets",
        "input_count",
        "output_count",
    }
    MODIFIER_FIELDS = {
        "object_name",
        "modifier_name",
        "group_name",
        "group_template",
        "group_created",
        "group_template_applied",
    }

    def _skill_md(self):
        return Path("src/dcc_mcp_blender/skills/blender-geometry-nodes/SKILL.md").read_text(encoding="utf-8")

    def _create(self, bpy, name, **kwargs):
        return load_and_call(f"{GEOMETRY_NODES_DIR}/scripts/create_geometry_node_group.py", bpy, name=name, **kwargs)

    def _add_modifier(self, bpy, **kwargs):
        return load_and_call(
            "blender-geometry-nodes/scripts/add_geometry_nodes_modifier.py",
            bpy,
            **kwargs,
        )

    def test_skill_md_lists_exactly_the_documented_fields(self):
        skill_md = self._skill_md()
        assert _documented_return_fields(skill_md, "create_geometry_node_group") == self.CREATE_FIELDS
        assert _documented_return_fields(skill_md, "add_geometry_nodes_modifier") == self.MODIFIER_FIELDS

    def test_create_geometry_node_group_returns_every_documented_field(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        created = self._create(bpy, "ContractGroup", template="pass_through")

        assert created["success"] is True
        assert _documented_return_fields(self._skill_md(), "create_geometry_node_group").issubset(created["context"])
        assert created["context"]["node_count"] == 2
        assert created["context"]["link_count"] == 1
        assert created["context"]["template_applied"] is True

    def test_add_geometry_nodes_modifier_returns_every_documented_field(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        bpy.data.objects.get.return_value = obj
        bpy.data.node_groups = FakeNodeGroups()

        result = self._add_modifier(bpy, object_name="Cube", group_name="Modifier Contract Group")

        assert result["success"] is True
        assert _documented_return_fields(self._skill_md(), "add_geometry_nodes_modifier").issubset(result["context"])
        # The modifier tool reports the group under a `group_` prefix.
        assert result["context"]["group_created"] is True
        assert result["context"]["group_template_applied"] is True
        assert result["context"]["group_template"] == "pass_through"

    def test_add_geometry_nodes_modifier_reports_no_graph_detail(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        bpy.data.objects.get.return_value = obj
        bpy.data.node_groups = FakeNodeGroups()

        result = self._add_modifier(bpy, object_name="Cube", group_name="No Graph Detail")

        assert result["success"] is True
        assert {"node_count", "link_count", "interface_sockets"}.isdisjoint(result["context"])

    def test_reused_group_reports_created_false(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        bpy.data.objects.get.return_value = obj
        bpy.data.node_groups = FakeNodeGroups()

        first = self._add_modifier(bpy, object_name="Cube", group_name="Reused Group")
        second = self._add_modifier(bpy, object_name="Cube", group_name="Reused Group")

        assert first["context"]["group_created"] is True
        assert second["success"] is True
        assert second["context"]["group_created"] is False


class TestGeometryNodeGroupTemplateReporting:
    """``template_applied`` must describe the wiring, not just the intent."""

    def _create(self, bpy, name, **kwargs):
        return load_and_call(f"{GEOMETRY_NODES_DIR}/scripts/create_geometry_node_group.py", bpy, name=name, **kwargs)

    def _broken_group(self, links):
        groups = FakeNodeGroups()
        group = FakeNodeGroup("BrokenGroup")
        group.links = links
        groups.append(group)
        return groups, group

    def test_unlinkable_sockets_report_template_not_applied(self):
        bpy = make_mock_bpy()
        groups, group = self._broken_group(FakeBrokenLinks())
        bpy.data.node_groups = groups

        created = self._create(bpy, "BrokenGroup", template="pass_through")

        assert created["success"] is True
        assert created["context"]["template_applied"] is False
        assert created["context"]["link_count"] == 0
        assert created["context"]["input_count"] == 1
        assert group.socket_names("INPUT") == ["Geometry"]

    def test_missing_link_api_reports_template_not_applied(self):
        bpy = make_mock_bpy()
        groups, _ = self._broken_group([])
        bpy.data.node_groups = groups

        created = self._create(bpy, "BrokenGroup", template="pass_through")

        assert created["success"] is True
        assert created["context"]["template_applied"] is False
        assert created["context"]["link_count"] == 0

    def test_wired_group_still_reports_template_applied(self):
        bpy = make_mock_bpy()
        bpy.data.node_groups = FakeNodeGroups()

        created = self._create(bpy, "WiredGroup", template="pass_through")

        assert created["context"]["template_applied"] is True
        assert created["context"]["link_count"] == 1


class TestInterfacePanelsAreNotSockets:
    """Blender 4.x ``items_tree`` mixes panels with sockets; only sockets are reported."""

    def _create(self, bpy, name, **kwargs):
        return load_and_call(f"{GEOMETRY_NODES_DIR}/scripts/create_geometry_node_group.py", bpy, name=name, **kwargs)

    def test_panel_with_item_type_is_excluded_from_interface_sockets(self):
        bpy = make_mock_bpy()
        groups = FakeNodeGroups()
        group = FakeNodeGroup("PanelGroup")
        groups.append(group)
        bpy.data.node_groups = groups
        group.interface.new_panel("Panel")

        created = self._create(bpy, "PanelGroup", template="pass_through")

        assert created["success"] is True
        assert created["context"]["interface_sockets"] == [
            {"name": "Geometry", "identifier": "Geometry", "in_out": "INPUT", "type": "NodeSocketGeometry"},
            {"name": "Geometry", "identifier": "Geometry", "in_out": "OUTPUT", "type": "NodeSocketGeometry"},
        ]
        assert created["context"]["input_count"] == 1
        assert created["context"]["output_count"] == 1
        assert created["context"]["link_count"] == 1

    def test_panel_without_item_type_is_excluded_from_interface_sockets(self):
        bpy = make_mock_bpy()
        groups = FakeNodeGroups()
        group = FakeNodeGroup("BarePanelGroup")
        groups.append(group)
        # A panel that predates ``item_type``: it has a name but neither ``in_out``
        # nor ``socket_type``, so it must not be mistaken for a socket.
        group.interface.append(SimpleNamespace(name="Panel"))
        bpy.data.node_groups = groups

        created = self._create(bpy, "BarePanelGroup", template="pass_through")

        assert created["success"] is True
        assert [record["name"] for record in created["context"]["interface_sockets"]] == ["Geometry", "Geometry"]
        assert [record["type"] for record in created["context"]["interface_sockets"]] == [
            "NodeSocketGeometry",
            "NodeSocketGeometry",
        ]

    def test_panel_is_excluded_from_evaluated_modifier_inputs(self):
        bpy = make_mock_bpy()
        obj = _make_mesh_obj()
        bpy.data.objects.get.return_value = obj
        groups = FakeNodeGroups()
        group = FakeNodeGroup("PanelGroup")
        groups.append(group)
        bpy.data.node_groups = groups

        self._create(bpy, "PanelGroup", template="pass_through")
        load_and_call(
            f"{GEOMETRY_NODES_DIR}/scripts/assign_geometry_node_group.py",
            bpy,
            object_name="Cube",
            group_name="PanelGroup",
        )
        group.interface.new_panel("Panel")

        info = load_and_call(
            f"{GEOMETRY_NODES_DIR}/scripts/evaluate_geometry_nodes_info.py",
            bpy,
            object_name="Cube",
            modifier_name="Geometry Nodes",
        )

        assert info["success"] is True
        assert [record["name"] for record in info["context"]["inputs"]] == ["Geometry", "Geometry"]
        assert all(record["type"] == "NodeSocketGeometry" for record in info["context"]["inputs"])


class TestGroupSocketDedupeIsTypeAware:
    """A same-name socket of another type is never silently reused."""

    def _create(self, bpy, name, **kwargs):
        return load_and_call(f"{GEOMETRY_NODES_DIR}/scripts/create_geometry_node_group.py", bpy, name=name, **kwargs)

    def test_clashing_socket_type_adds_a_numbered_geometry_socket(self):
        bpy = make_mock_bpy()
        groups = FakeNodeGroups()
        group = FakeNodeGroup("ClashGroup")
        groups.append(group)
        bpy.data.node_groups = groups
        group.interface.items_tree.new_socket("Geometry", "INPUT", "NodeSocketFloat")

        created = self._create(bpy, "ClashGroup", template="pass_through")

        assert created["success"] is True
        geometry_inputs = [
            socket
            for socket in group.interface.sockets()
            if socket.in_out == "INPUT" and socket.socket_type == "NodeSocketGeometry"
        ]
        assert len(geometry_inputs) == 1
        assert geometry_inputs[0].name == "Geometry.001"
        # The caller's Float socket is left exactly as it was.
        assert [socket.name for socket in group.interface.sockets() if socket.socket_type == "NodeSocketFloat"] == [
            "Geometry"
        ]

    def test_clashing_socket_type_still_wires_geometry_to_geometry(self):
        bpy = make_mock_bpy()
        groups = FakeNodeGroups()
        group = FakeNodeGroup("ClashGroup")
        groups.append(group)
        bpy.data.node_groups = groups
        group.interface.items_tree.new_socket("Geometry", "INPUT", "NodeSocketFloat")

        self._create(bpy, "ClashGroup", template="pass_through")

        assert len(group.links) == 1
        assert group.links[0].from_socket.socket_type == "NodeSocketGeometry"
        assert group.links[0].to_socket.socket_type == "NodeSocketGeometry"

    def test_matching_socket_type_is_still_reused(self):
        bpy = make_mock_bpy()
        groups = FakeNodeGroups()
        group = FakeNodeGroup("TypedGroup")
        groups.append(group)
        bpy.data.node_groups = groups
        group.interface.items_tree.new_socket("Geometry", "INPUT", "NodeSocketGeometry")

        self._create(bpy, "TypedGroup", template="pass_through")

        assert group.socket_names("INPUT") == ["Geometry"]
        assert group.socket_names("OUTPUT") == ["Geometry"]

    def test_legacy_short_socket_type_is_not_treated_as_a_clash(self):
        bpy = make_mock_bpy()
        groups = FakeNodeGroups()
        legacy = FakeLegacyNodeGroup("LegacyTypedGroup")
        # Blender 3.6 reports short type codes ("GEOMETRY") where 4.x reports
        # "NodeSocketGeometry"; that naming difference is not a type change.
        legacy.inputs.append(FakeLegacySocket("Geometry", "GEOMETRY", is_output=False))
        groups.append(legacy)
        bpy.data.node_groups = groups

        created = self._create(bpy, "LegacyTypedGroup", template="pass_through")

        assert created["success"] is True
        assert [socket.name for socket in legacy.inputs] == ["Geometry"]
        assert [_socket_type_of(socket) for socket in legacy.inputs] == ["GEOMETRY"]
        assert len(legacy.links) == 1

    def test_legacy_clashing_short_type_adds_a_numbered_geometry_socket(self):
        bpy = make_mock_bpy()
        groups = FakeNodeGroups()
        legacy = FakeLegacyNodeGroup("LegacyClashGroup")
        # "VALUE" is a Float on 3.6, so reusing it as the pass-through Geometry
        # input would wire the backbone to the wrong socket type.
        legacy.inputs.append(FakeLegacySocket("Geometry", "VALUE", "INPUT"))
        groups.append(legacy)
        bpy.data.node_groups = groups

        created = self._create(bpy, "LegacyClashGroup", template="pass_through")

        assert created["success"] is True
        assert created["context"]["template_applied"] is True
        assert [socket.name for socket in legacy.inputs] == ["Geometry", "Geometry.001"]
        assert [_socket_type_of(socket) for socket in legacy.inputs] == ["VALUE", "NodeSocketGeometry"]
        assert len(legacy.links) == 1
        assert legacy.links[0].from_socket.name == "Geometry.001"
        assert legacy.links[0].from_socket.socket_type == "NodeSocketGeometry"
