"""Tests for the physical toy-material skill contract."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from dcc_mcp_blender._photographic_material_ops import (
    _image_has_alpha,
    _is_polyhaven_source,
    _linked_from,
    _pbr_link_state,
    _pbr_texture_nodes,
    _uses_object_coordinates,
    configure_photographic_material,
)


def test_plant_material_requires_a_diffuse_scan_for_alpha_cutout():
    result = configure_photographic_material(material_name="Leaf", material_kind="PLANT_LEAF")

    assert result["success"] is False
    assert "diffuse scan" in result["error"]


def test_material_polyhaven_source_matching_rejects_lookalike_domains():
    assert _is_polyhaven_source("Poly Haven") is True
    assert _is_polyhaven_source("https://polyhaven.com/asset/sky") is True
    assert _is_polyhaven_source("https://not-polyhaven.com/sky.hdr") is False


def test_image_alpha_validation_reads_png_channel_type(tmp_path):
    def png_header(color_type):
        header = bytearray(29)
        header[:8] = b"\x89PNG\r\n\x1a\n"
        header[25] = color_type
        return bytes(header)

    rgba = tmp_path / "rgba.png"
    rgb = tmp_path / "rgb.png"
    rgba.write_bytes(png_header(6))
    rgb.write_bytes(png_header(2))

    assert _image_has_alpha(SimpleNamespace(filepath=str(rgba), channels=4)) is True
    assert _image_has_alpha(SimpleNamespace(filepath=str(rgb), channels=4)) is False


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


def test_pbr_link_validation_accepts_a_normal_map_followed_by_surface_bump():
    def socket(name):
        return SimpleNamespace(name=name, links=[])

    def node(name, node_type, inputs=(), outputs=()):
        return SimpleNamespace(
            name=name,
            type=node_type,
            inputs=list(inputs),
            outputs=list(outputs),
        )

    diffuse_output = socket("Color")
    roughness_output = socket("Color")
    normal_texture_output = socket("Color")
    diffuse = node("DCC Photo Diffuse Texture", "TEX_IMAGE", outputs=(diffuse_output,))
    roughness = node("DCC Photo Roughness Texture", "TEX_IMAGE", outputs=(roughness_output,))
    normal_texture = node("DCC Photo Normal Texture", "TEX_IMAGE", outputs=(normal_texture_output,))
    normal_map_color = socket("Color")
    normal_map_output = socket("Normal")
    normal_map = node(
        "DCC Photo Normal Map",
        "NORMAL_MAP",
        inputs=(normal_map_color,),
        outputs=(normal_map_output,),
    )
    bump_normal = socket("Normal")
    bump_output = socket("Normal")
    bump = node(
        "DCC Photo Fine Surface Bump",
        "BUMP",
        inputs=(bump_normal,),
        outputs=(bump_output,),
    )
    principled_base = socket("Base Color")
    principled_roughness = socket("Roughness")
    principled_normal = socket("Normal")
    principled = node(
        "Principled BSDF",
        "BSDF_PRINCIPLED",
        inputs=(principled_base, principled_roughness, principled_normal),
    )

    def link(source_node, source_socket, target_socket):
        target_socket.links.append(SimpleNamespace(from_node=source_node, from_socket=source_socket))

    link(diffuse, diffuse_output, principled_base)
    link(roughness, roughness_output, principled_roughness)
    link(normal_texture, normal_texture_output, normal_map_color)
    link(normal_map, normal_map_output, bump_normal)
    link(bump, bump_output, principled_normal)

    state = _pbr_link_state(SimpleNamespace(nodes=[diffuse, roughness, normal_texture, normal_map, bump, principled]))

    assert state == {"diffuse": True, "roughness": True, "normal": True}

    bump_normal.links.clear()
    assert (
        _pbr_link_state(SimpleNamespace(nodes=[diffuse, roughness, normal_texture, normal_map, bump, principled]))[
            "normal"
        ]
        is False
    )


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
        tools["configure_photographic_material"]["input_schema"]["properties"]["normal_map_convention"]["const"]
        == "OPENGL"
    )
    assert (
        tools["configure_photographic_material"]["input_schema"]["properties"]["texture_paths"]["additionalProperties"]
        is False
    )
    assert (
        tools["validate_photographic_material"]["input_schema"]["properties"]["require_pbr_textures"]["default"] is True
    )
