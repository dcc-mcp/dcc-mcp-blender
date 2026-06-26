"""Unit tests for blender-node-graph skill scripts (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

NODE_GRAPH_PATH = "src/dcc_mcp_blender/skills/blender-node-graph/tools.yaml"


def _make_scene_with_compositor(use_nodes=True):
    scene = MagicMock()
    scene.name = "Scene"
    scene.use_nodes = use_nodes
    if use_nodes:
        node_tree = MagicMock()
        node_tree.nodes = []
        node_tree.links = []
        scene.node_tree = node_tree
    else:
        scene.node_tree = None
    return scene


def _make_material(name="Material", use_nodes=True):
    mat = MagicMock()
    mat.name = name
    mat.use_nodes = use_nodes
    if use_nodes:
        mat.node_tree = MagicMock()
        mat.node_tree.nodes = []
        mat.node_tree.links = []
    else:
        mat.node_tree = None
    return mat


def test_get_compositor_node_tree_enabled():
    bpy = make_mock_bpy()
    scene = _make_scene_with_compositor(use_nodes=True)
    bpy.context.scene = scene

    result = load_and_call("blender-node-graph/scripts/get_compositor_node_tree.py", bpy)
    assert result["success"] is True
    assert result["context"]["node_count"] == 0


def test_get_compositor_node_tree_disabled():
    bpy = make_mock_bpy()
    scene = _make_scene_with_compositor(use_nodes=False)
    bpy.context.scene = scene

    result = load_and_call("blender-node-graph/scripts/get_compositor_node_tree.py", bpy)
    assert result["success"] is False
    assert "not enabled" in result["message"].lower()


def test_list_all_node_graphs_empty():
    bpy = make_mock_bpy()
    scene = _make_scene_with_compositor(use_nodes=False)
    bpy.context.scene = scene
    bpy.data.materials.__iter__ = MagicMock(return_value=iter([]))
    bpy.data.node_groups.__iter__ = MagicMock(return_value=iter([]))

    result = load_and_call("blender-node-graph/scripts/list_all_node_graphs.py", bpy)
    assert result["success"] is True
    assert result["context"]["count"] == 0


def test_list_all_node_graphs_with_material():
    bpy = make_mock_bpy()
    scene = _make_scene_with_compositor(use_nodes=False)
    bpy.context.scene = scene

    mat = _make_material("TestMat")
    bpy.data.materials.__iter__ = MagicMock(return_value=iter([mat]))
    bpy.data.node_groups.__iter__ = MagicMock(return_value=iter([]))

    result = load_and_call("blender-node-graph/scripts/list_all_node_graphs.py", bpy)
    assert result["success"] is True
    assert result["context"]["count"] >= 1
    assert any(g["kind"] == "shader" for g in result["context"]["node_graphs"])


def test_tools_yaml_declares_tools():
    doc = yaml.safe_load(Path(NODE_GRAPH_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {"get_compositor_node_tree", "list_all_node_graphs", "list_compositor_nodes"}.issubset(tools)
    for tool in tools.values():
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert "annotations" in tool
