"""Unit tests for blender-shader-nodes skill scripts (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

SHADER_NODES_DIR = "blender-shader-nodes"
SHADER_NODES_PATH = "src/dcc_mcp_blender/skills/blender-shader-nodes/tools.yaml"


class FakeSocket(SimpleNamespace):
    def __init__(self, name, default_value=None, socket_type="VALUE"):
        super().__init__(
            name=name,
            identifier=name,
            default_value=default_value,
            type=socket_type,
            is_linked=False,
            node=None,
        )


class FakeNode:
    def __init__(self, name, node_type, inputs=None, outputs=None):
        self.name = name
        self.type = node_type
        self.bl_idname = node_type
        self.label = ""
        self.location = [0.0, 0.0]
        self.inputs = inputs or {}
        self.outputs = outputs or {}
        for socket in [*self.inputs.values(), *self.outputs.values()]:
            socket.node = self


class FakeNodes(list):
    def get(self, name):
        return next((node for node in self if node.name == name), None)

    def new(self, type):  # noqa: A002
        if type == "ShaderNodeValue":
            node = FakeNode("Value", type, outputs={"Value": FakeSocket("Value", 0.0)})
        elif type == "ShaderNodeTexImage":
            node = FakeNode("Image Texture", type, outputs={"Color": FakeSocket("Color", [1.0, 1.0, 1.0, 1.0])})
        elif type == "ShaderNodeEmission":
            node = FakeNode(
                "Emission",
                type,
                inputs={"Color": FakeSocket("Color", [1.0, 1.0, 1.0, 1.0])},
                outputs={"Emission": FakeSocket("Emission")},
            )
        else:
            node = FakeNode(type, type)
        self.append(node)
        return node

    def remove(self, node):
        self[:] = [item for item in self if item is not node]


class FakeLinks(list):
    def new(self, from_socket, to_socket):
        from_socket.is_linked = True
        to_socket.is_linked = True
        link = SimpleNamespace(
            from_node=from_socket.node,
            from_socket=from_socket,
            to_node=to_socket.node,
            to_socket=to_socket,
        )
        self.append(link)
        return link

    def remove(self, link):
        self[:] = [item for item in self if item is not link]


def _nodes_collection(nodes):
    return FakeNodes(nodes)


def _make_material(name="ShaderMat", use_nodes=True):
    mat = MagicMock()
    mat.name = name
    mat.use_nodes = use_nodes

    bsdf = FakeNode("Principled BSDF", "BSDF_PRINCIPLED")
    bsdf.inputs = {
        "Base Color": FakeSocket("Base Color", [1.0, 1.0, 1.0, 1.0], "RGBA"),
        "Metallic": FakeSocket("Metallic", 0.0),
        "Roughness": FakeSocket("Roughness", 0.5),
    }
    bsdf.outputs = {"BSDF": FakeSocket("BSDF")}

    output = FakeNode("Material Output", "OUTPUT_MATERIAL", inputs={"Surface": FakeSocket("Surface")})
    for socket in [*bsdf.inputs.values(), *bsdf.outputs.values(), *output.inputs.values()]:
        socket.node = bsdf if socket in [*bsdf.inputs.values(), *bsdf.outputs.values()] else output

    mat.node_tree.nodes = _nodes_collection([bsdf, output])
    mat.node_tree.links = FakeLinks()
    return mat, bsdf


def test_shader_nodes_tools_yaml_declares_modern_contracts():
    raw_tools = Path(SHADER_NODES_PATH).read_text(encoding="utf-8")
    assert "<<:" not in raw_tools
    doc = yaml.safe_load(raw_tools)
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {
        "list_node_trees",
        "list_nodes",
        "create_node",
        "delete_node",
        "list_node_sockets",
        "connect_nodes",
        "disconnect_nodes",
        "list_node_links",
        "set_node_input",
        "get_node_value",
        "create_material_with_nodes",
        "assign_texture_node",
        "set_principled_inputs",
    }.issubset(tools)
    for tool in tools.values():
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert tool["input_schema"]["type"] == "object"
        assert tool["output_schema"]["properties"]["success"]["type"] == "boolean"
        assert "annotations" in tool


class TestListMaterialNodes:
    def test_lists_nodes_and_sockets(self):
        bpy = make_mock_bpy()
        mat, _bsdf = _make_material("ShaderMat")
        bpy.data.materials.get.return_value = mat

        result = load_and_call(
            "blender-shader-nodes/scripts/list_material_nodes.py",
            bpy,
            material_name="ShaderMat",
        )

        assert result["success"] is True
        assert result["context"]["count"] == 2
        assert result["context"]["nodes"][0]["name"] == "Principled BSDF"
        assert result["context"]["nodes"][0]["inputs"][0]["name"] == "Base Color"

    def test_material_not_found(self):
        bpy = make_mock_bpy()
        bpy.data.materials.get.return_value = None

        result = load_and_call(
            "blender-shader-nodes/scripts/list_material_nodes.py",
            bpy,
            material_name="Ghost",
        )

        assert result["success"] is False


class TestNodeGraphTools:
    def test_create_set_connect_get_delete_shader_node(self):
        bpy = make_mock_bpy()
        mat, bsdf = _make_material("ShaderMat")
        bpy.data.materials.get.return_value = mat
        bpy.data.materials.__iter__ = MagicMock(return_value=iter([mat]))
        ref = {"kind": "shader", "material_name": "ShaderMat"}

        listed_trees = load_and_call(f"{SHADER_NODES_DIR}/scripts/list_node_trees.py", bpy, kind="shader")
        assert listed_trees["success"] is True
        assert listed_trees["context"]["count"] == 1

        created = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/create_node.py",
            bpy,
            node_tree_ref=ref,
            node_type="ShaderNodeValue",
            name="Metallic Value",
        )
        assert created["success"] is True

        set_value = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/set_node_input.py",
            bpy,
            node_tree_ref=ref,
            node_name="Principled BSDF",
            socket="Metallic",
            value=0.42,
        )
        assert set_value["success"] is True
        assert bsdf.inputs["Metallic"].default_value == 0.42

        connected = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/connect_nodes.py",
            bpy,
            node_tree_ref=ref,
            from_node="Metallic Value",
            from_socket="Value",
            to_node="Principled BSDF",
            to_socket="Metallic",
        )
        assert connected["success"] is True
        assert len(mat.node_tree.links) == 1

        links = load_and_call(f"{SHADER_NODES_DIR}/scripts/list_node_links.py", bpy, node_tree_ref=ref)
        assert links["context"]["count"] == 1

        value = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/get_node_value.py",
            bpy,
            node_tree_ref=ref,
            node_name="Principled BSDF",
            socket="Metallic",
        )
        assert value["context"]["value"] == 0.42

        disconnected = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/disconnect_nodes.py",
            bpy,
            node_tree_ref=ref,
            from_node="Metallic Value",
            to_node="Principled BSDF",
        )
        assert disconnected["success"] is True
        assert len(mat.node_tree.links) == 0

        deleted = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/delete_node.py",
            bpy,
            node_tree_ref=ref,
            node_name="Metallic Value",
        )
        assert deleted["success"] is True

    def test_bad_socket_returns_error(self):
        bpy = make_mock_bpy()
        mat, _bsdf = _make_material("ShaderMat")
        bpy.data.materials.get.return_value = mat

        result = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/connect_nodes.py",
            bpy,
            node_tree_ref={"kind": "shader", "material_name": "ShaderMat"},
            from_node="Principled BSDF",
            from_socket="Not Real",
            to_node="Material Output",
            to_socket="Surface",
        )

        assert result["success"] is False

    def test_assign_texture_node_requires_existing_image(self, tmp_path):
        bpy = make_mock_bpy()
        mat, _bsdf = _make_material("ShaderMat")
        bpy.data.materials.get.return_value = mat
        image = SimpleNamespace(name="albedo.png")
        bpy.data.images.load.return_value = image
        texture = tmp_path / "albedo.png"
        texture.write_bytes(b"png")

        result = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/assign_texture_node.py",
            bpy,
            material_name="ShaderMat",
            image_path=str(texture),
        )

        assert result["success"] is True
        bpy.data.images.load.assert_called_once()

        missing = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/assign_texture_node.py",
            bpy,
            material_name="ShaderMat",
            image_path=str(tmp_path / "missing.png"),
        )
        assert missing["success"] is False


class TestSetPrincipledInput:
    def test_sets_scalar_input(self):
        bpy = make_mock_bpy()
        mat, bsdf = _make_material("ShaderMat")
        bpy.data.materials.get.return_value = mat

        result = load_and_call(
            "blender-shader-nodes/scripts/set_principled_input.py",
            bpy,
            material_name="ShaderMat",
            input_name="Metallic",
            value=0.8,
        )

        assert result["success"] is True
        assert bsdf.inputs["Metallic"].default_value == 0.8

    def test_expands_rgb_color_to_rgba(self):
        bpy = make_mock_bpy()
        mat, bsdf = _make_material("ShaderMat")
        bpy.data.materials.get.return_value = mat

        result = load_and_call(
            "blender-shader-nodes/scripts/set_principled_input.py",
            bpy,
            material_name="ShaderMat",
            input_name="Base Color",
            value=[0.1, 0.2, 0.3],
        )

        assert result["success"] is True
        assert bsdf.inputs["Base Color"].default_value == [0.1, 0.2, 0.3, 1.0]

    def test_missing_input_returns_error(self):
        bpy = make_mock_bpy()
        mat, _bsdf = _make_material("ShaderMat")
        bpy.data.materials.get.return_value = mat

        result = load_and_call(
            "blender-shader-nodes/scripts/set_principled_input.py",
            bpy,
            material_name="ShaderMat",
            input_name="Not Real",
            value=1.0,
        )

        assert result["success"] is False

    def test_sets_multiple_principled_inputs(self):
        bpy = make_mock_bpy()
        mat, bsdf = _make_material("ShaderMat")
        bpy.data.materials.get.return_value = mat

        result = load_and_call(
            f"{SHADER_NODES_DIR}/scripts/set_principled_inputs.py",
            bpy,
            material_name="ShaderMat",
            inputs={"Metallic": 0.7, "Roughness": 0.2},
        )

        assert result["success"] is True
        assert bsdf.inputs["Metallic"].default_value == 0.7
        assert bsdf.inputs["Roughness"].default_value == 0.2
