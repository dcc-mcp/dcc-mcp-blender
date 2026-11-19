"""Tests for the physical toy-material skill contract."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from dcc_mcp_blender._photographic_material_ops import (
    _linked_from,
    _pbr_texture_nodes,
    _uses_object_coordinates,
    configure_photographic_material,
)


def test_plant_material_requires_a_diffuse_scan_for_alpha_cutout():
    result = configure_photographic_material(material_name="Leaf", material_kind="PLANT_LEAF")

    assert result["success"] is False
    assert "diffuse scan" in result["error"]


def test_pbr_validation_resolves_each_required_map_and_object_coordinates():
    coordinate_node = SimpleNamespace(type="TEX_COORD")
    object_socket = SimpleNamespace(name="Object")
    vector_socket = SimpleNamespace(
        name="Vector",
        links=[SimpleNamespace(from_node=coordinate_node, from_socket=object_socket)],
    )
    nodes = [
        SimpleNamespace(
            name=f"DCC Photo {map_name.title()} Texture",
            type="TEX_IMAGE",
            inputs=[vector_socket],
        )
        for map_name in ("diffuse", "roughness", "normal")
    ]

    resolved = _pbr_texture_nodes(SimpleNamespace(nodes=nodes))

    assert set(resolved) == {"diffuse", "roughness", "normal"}
    assert all(_uses_object_coordinates(node) for node in resolved.values())


def test_leaf_link_validation_accepts_equivalent_blender_node_wrappers():
    source = SimpleNamespace(as_pointer=lambda: 7)
    wrapper = SimpleNamespace(as_pointer=lambda: 7)
    socket = SimpleNamespace(name="Alpha")
    target = SimpleNamespace(links=[SimpleNamespace(from_node=wrapper, from_socket=socket)])

    assert _linked_from(target, source, "Alpha") is True


def test_tools_yaml_declares_material_and_bevel_contracts():
    path = Path("src/dcc_mcp_blender/skills/blender-photographic-materials/tools.yaml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in document["tools"]}

    assert set(tools) == {
        "configure_photographic_material",
        "configure_toy_bevel",
        "validate_photographic_material",
    }
    assert tools["configure_toy_bevel"]["input_schema"]["properties"]["width_mm"]["minimum"] == 0.3
    assert tools["configure_toy_bevel"]["input_schema"]["properties"]["segments"]["const"] == 3
    assert tools["configure_photographic_material"]["input_schema"]["properties"]["texture_source"]["type"] == "string"
    assert (
        tools["configure_photographic_material"]["input_schema"]["properties"]["texture_paths"]["additionalProperties"]
        is False
    )
