"""Tests for the physical toy-material skill contract."""

from __future__ import annotations

from pathlib import Path

import yaml

from dcc_mcp_blender._photographic_material_ops import configure_photographic_material


def test_plant_material_requires_a_diffuse_scan_for_alpha_cutout():
    result = configure_photographic_material(material_name="Leaf", material_kind="PLANT_LEAF")

    assert result["success"] is False
    assert "diffuse scan" in result["error"]


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
    assert (
        tools["configure_photographic_material"]["input_schema"]["properties"]["texture_paths"]["additionalProperties"]
        is False
    )
