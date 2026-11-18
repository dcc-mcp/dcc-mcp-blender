"""Tests for the motivated photographic lighting contract."""

from __future__ import annotations

from pathlib import Path

import yaml

from dcc_mcp_blender._photographic_lighting_ops import configure_motivated_lighting


def test_outdoor_lighting_requires_an_hdri_path():
    result = configure_motivated_lighting(source_name="Outdoor", source_type="OUTDOOR_HDRI")

    assert result["success"] is False
    assert "hdri_path" in result["error"]


def test_tools_yaml_declares_motivated_lighting_contract():
    path = Path("src/dcc_mcp_blender/skills/blender-photographic-lighting/tools.yaml")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in document["tools"]}

    assert set(tools) == {"configure_motivated_lighting", "validate_motivated_lighting"}
    assert "OUTDOOR_HDRI" in tools["configure_motivated_lighting"]["input_schema"]["properties"]["source_type"]["enum"]
    assert tools["validate_motivated_lighting"]["read_only"] is True
