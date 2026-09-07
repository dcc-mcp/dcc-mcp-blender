"""Live-host regressions for bounded RNA discovery and modifier readback."""

from __future__ import annotations

import json

import pytest

bpy = pytest.importorskip("bpy")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


def _call(stem, **kwargs):
    result = load_skill("blender-rna", stem).main(**kwargs)
    assert result["success"], result
    # The envelope must be usable by both MCP and CLI, without bpy wrappers.
    json.dumps(result, allow_nan=False)
    context = result["context"]
    assert context["blender_version"] == bpy.app.version_string
    assert context["schema"] == "dcc-mcp-blender.rna-query.v1"
    return context


def test_live_rna_discovery_pages_and_current_schema():
    first = _call("search_rna_types", query="modifier", limit=1)
    assert len(first["types"]) == 1
    assert first["next_offset"] == 1
    second = _call("search_rna_types", query="modifier", offset=1, limit=1)
    assert first["types"][0]["identifier"] != second["types"][0]["identifier"]
    assert first["total"] == second["total"]

    result = _call("describe_rna_type", type_name="SolidifyModifier", query="thickness")
    properties = {row["identifier"]: row for row in result["properties"]}
    thickness = properties["thickness"]
    assert thickness["type"] == "FLOAT"
    assert not thickness["is_readonly"]
    assert thickness["limits"]["hard_min"] < 0 < thickness["limits"]["hard_max"]

    enum = _call("describe_rna_type", type_name="SubsurfModifier", query="subdivision_type")
    items = enum["properties"][0]["enum_items"]
    assert {item["identifier"] for item in items} >= {"CATMULL_CLARK", "SIMPLE"}


def test_live_modifier_values_are_explicit_and_read_only():
    mesh = bpy.data.meshes.new("RNAQueryFixture")
    obj = bpy.data.objects.new("RNAQueryFixture", mesh)
    bpy.context.scene.collection.objects.link(obj)
    try:
        solidify = obj.modifiers.new("Query Solidify", "SOLIDIFY")
        solidify.thickness = 0.375
        mirror = obj.modifiers.new("Query Mirror", "MIRROR")
        mirror.use_axis = (True, False, True)
        before = (
            tuple(bpy.data.objects.keys()),
            tuple(item.name for item in bpy.context.selected_objects),
            bpy.context.view_layer.objects.active,
            bpy.context.scene.frame_current,
            obj.matrix_world.copy(),
            tuple(item.name for item in obj.modifiers),
        )
        values = _call(
            "get_modifier_values",
            object_name=obj.name,
            modifier_name=solidify.name,
            properties=["thickness", "no_such_property"],
        )["properties"]
        assert values["thickness"]["status"] == "available"
        assert values["thickness"]["value"] == pytest.approx(0.375)
        assert values["no_such_property"]["status"] == "unavailable"
        assert "value" not in values["no_such_property"]
        mirror_values = _call(
            "get_modifier_values",
            object_name=obj.name,
            modifier_name=mirror.name,
            properties=["use_axis", "mirror_object"],
        )["properties"]
        assert mirror_values["use_axis"]["value"] == [True, False, True]
        assert mirror_values["mirror_object"]["status"] == "unsupported"
        assert "value" not in mirror_values["mirror_object"]
        assert before == (
            tuple(bpy.data.objects.keys()),
            tuple(item.name for item in bpy.context.selected_objects),
            bpy.context.view_layer.objects.active,
            bpy.context.scene.frame_current,
            obj.matrix_world.copy(),
            tuple(item.name for item in obj.modifiers),
        )
        assert solidify.thickness == pytest.approx(0.375)
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def test_live_rna_queries_reject_expressions_and_unknown_types():
    for name in ("__class__", "bpy.data.objects", "SolidifyModifier()", "NoSuchRNAType"):
        result = load_skill("blender-rna", "describe_rna_type").main(type_name=name)
        assert not result["success"], result
