"""Unit tests for blender-shader-nodes skill scripts (bpy mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


def _nodes_collection(nodes):
    collection = MagicMock()
    collection.__iter__ = MagicMock(return_value=iter(nodes))
    by_name = {node.name: node for node in nodes}
    collection.get = MagicMock(side_effect=lambda name: by_name.get(name))
    return collection


def _make_material(name="ShaderMat", use_nodes=True):
    mat = MagicMock()
    mat.name = name
    mat.use_nodes = use_nodes

    bsdf = MagicMock()
    bsdf.name = "Principled BSDF"
    bsdf.type = "BSDF_PRINCIPLED"
    bsdf.label = ""
    bsdf.inputs = {
        "Base Color": MagicMock(default_value=[1.0, 1.0, 1.0, 1.0]),
        "Metallic": MagicMock(default_value=0.0),
        "Roughness": MagicMock(default_value=0.5),
    }
    bsdf.outputs = {"BSDF": MagicMock(name="BSDF")}

    output = MagicMock()
    output.name = "Material Output"
    output.type = "OUTPUT_MATERIAL"
    output.label = ""
    output.inputs = {"Surface": MagicMock(name="Surface")}
    output.outputs = {}

    mat.node_tree.nodes = _nodes_collection([bsdf, output])
    return mat, bsdf


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
        assert "Base Color" in result["context"]["nodes"][0]["inputs"]

    def test_material_not_found(self):
        bpy = make_mock_bpy()
        bpy.data.materials.get.return_value = None

        result = load_and_call(
            "blender-shader-nodes/scripts/list_material_nodes.py",
            bpy,
            material_name="Ghost",
        )

        assert result["success"] is False


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
