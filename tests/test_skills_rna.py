"""RNA contract tests with strict fakes; no real Blender installation required."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import yaml

from tests.conftest import load_and_call

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "src/dcc_mcp_blender/skills/blender-rna"


class Properties(list):
    def get(self, identifier):
        return next((prop for prop in self if prop.identifier == identifier), None)


def property_info(identifier, kind="INT", **kwargs):
    return SimpleNamespace(
        **dict(
            dict(
                identifier=identifier,
                name=identifier.replace("_", " ").title(),
                description="A host property",
                type=kind,
                is_readonly=False,
                is_array=False,
                array_length=0,
                is_runtime=False,
            ),
            **kwargs,
        )
    )


def runtime(properties=(), values=None):
    rna = SimpleNamespace(
        identifier="SubsurfModifier",
        name="Subdivision Surface Modifier",
        description="Subdivide geometry",
        properties=Properties(properties),
    )
    modifier = SimpleNamespace(name="Subdivision", bl_rna=rna, **(values or {}))
    obj = SimpleNamespace(name="Cube", modifiers={"Subdivision": modifier})
    bpy = SimpleNamespace(
        app=SimpleNamespace(version_string="4.2.10"),
        types=SimpleNamespace(SubsurfModifier=SimpleNamespace(bl_rna=rna)),
        data=SimpleNamespace(objects={"Cube": obj}),
        ops=Mock(side_effect=AssertionError("Operators must not be called")),
    )
    return bpy


def call(tool, bpy=None, **kwargs):
    return load_and_call("blender-rna/scripts/{}.py".format(tool), bpy or runtime(), **kwargs)


def test_search_is_runtime_versioned_filtered_and_paginated():
    bpy = runtime()
    bpy.types.OtherModifier = SimpleNamespace(
        bl_rna=SimpleNamespace(identifier="OtherModifier", name="Other", description="Modifier")
    )
    bpy.types.Alias = bpy.types.SubsurfModifier
    bpy.types._Private = SimpleNamespace(bl_rna=SimpleNamespace(identifier="_Private"))
    first = call("search_rna_types", bpy, query="modifier", limit=1)["context"]
    assert first["blender_version"] == "4.2.10"
    assert first["schema"] == "dcc-mcp-blender.rna-query.v1"
    assert [row["identifier"] for row in first["types"]] == ["OtherModifier"]
    assert first["next_offset"] == 1
    assert first["total"] == 2
    assert first["truncated"] is True
    second = call("search_rna_types", bpy, query="MODIFIER", offset=1, limit=1)["context"]
    assert second["types"][0]["identifier"] == "SubsurfModifier"
    assert second["next_offset"] is None
    assert second["truncated"] is False
    assert call("search_rna_types", bpy, query="does-not-exist")["context"]["types"] == []
    bpy.ops.assert_not_called()


def test_search_observes_new_runtime_types_without_cache():
    bpy = runtime()
    assert call("search_rna_types", bpy, query="New")["context"]["types"] == []
    bpy.types.NewType = SimpleNamespace(bl_rna=SimpleNamespace(identifier="NewType", name="New", description=""))
    assert call("search_rna_types", bpy, query="New")["context"]["types"][0]["identifier"] == "NewType"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": True},
        {"limit": 1.5},
        {"offset": -1},
        {"offset": 100001},
        {"offset": True},
        {"offset": "1"},
        {"query": None},
        {"query": "x" * 129},
        {"query": "hello\nworld"},
    ],
)
def test_page_bounds_enforced_without_schema_validation(kwargs):
    assert call("search_rna_types", **kwargs)["success"] is False
    assert call("describe_rna_type", type_name="SubsurfModifier", **kwargs)["success"] is False


@pytest.mark.parametrize("name", ["", "_Private", "__class__", "bpy.types.Object", "Object()", "x[0]", "a" * 129, 123])
def test_type_identifiers_reject_paths_private_names_and_expressions(name):
    assert call("describe_rna_type", type_name=name)["success"] is False


def test_describe_reports_finite_limits_readonly_and_property_pages():
    props = [
        property_info("render_levels", hard_min=0, hard_max=11, soft_min=0, soft_max=6, is_readonly=True),
        property_info("levels", hard_min=float("-inf"), hard_max=11),
        property_info("rna_type", "POINTER"),
        property_info("_private"),
    ]
    bpy = runtime(props)
    ctx = call("describe_rna_type", bpy, type_name="SubsurfModifier", query="levels", limit=1)["context"]
    assert ctx["total"] == 2
    assert ctx["properties"][0]["identifier"] == "levels"
    assert ctx["properties"][0]["limits"] == {"hard_max": 11}
    assert ctx["next_offset"] == 1
    second = call("describe_rna_type", bpy, type_name="SubsurfModifier", offset=1)["context"]
    assert second["properties"][0]["is_readonly"] is True
    json.dumps(ctx, allow_nan=False)


def test_describe_enum_metadata_is_static_only_and_bounded():
    class EnumInfo:
        identifier = "method"
        type = "ENUM"
        is_readonly = False
        enum_items_static = [SimpleNamespace(identifier=str(n), name="Option", description="") for n in range(70)]

        @property
        def enum_items(self):
            raise AssertionError("Dynamic enum callbacks must not be accessed")

    row = call("describe_rna_type", runtime([EnumInfo()]), type_name="SubsurfModifier")["context"]["properties"][0]
    assert len(row["enum_items"]) == 64
    assert row["enum_truncated"] is True
    assert row["enum_status"] == "static_only"


def test_static_enum_unavailable_is_explicit():
    row = call("describe_rna_type", runtime([property_info("method", "ENUM")]), type_name="SubsurfModifier")["context"][
        "properties"
    ][0]
    assert row["enum_status"] == "unavailable"
    assert row["enum_items"] == []


def test_modifier_readback_returns_scalars_arrays_and_sorted_flags():
    props = [
        property_info("levels"),
        property_info("weight", "FLOAT"),
        property_info("visible", "BOOLEAN"),
        property_info("label", "STRING"),
        property_info("mode", "ENUM"),
        property_info("axis", "BOOLEAN", is_array=True, array_length=3),
        property_info("flags", "ENUM", is_enum_flag=True),
    ]
    values = {
        "levels": 2,
        "weight": 0.5,
        "visible": True,
        "label": "Name",
        "mode": "ONE",
        "axis": [True, False, True],
        "flags": {"B", "A"},
    }
    bpy = runtime(props, values)
    ctx = call("get_modifier_values", bpy, object_name="Cube", modifier_name="Subdivision", properties=list(values))[
        "context"
    ]
    assert ctx["type_name"] == "SubsurfModifier"
    assert ctx["object_name"] == "Cube"
    for name, expected in values.items():
        row = ctx["properties"][name]
        assert row["status"] == "available"
        assert row["value"] == (sorted(expected) if isinstance(expected, set) else expected)
    bpy.ops.assert_not_called()


def test_pointer_collection_and_runtime_properties_are_not_read():
    class Modifier:
        name = "Subdivision"
        bl_rna = SimpleNamespace(
            identifier="SubsurfModifier",
            properties=Properties(
                [
                    property_info("target", "POINTER"),
                    property_info("items", "COLLECTION"),
                    property_info("custom", "INT", is_runtime=True),
                    property_info("large", "FLOAT", is_array=True, array_length=100),
                ]
            ),
        )

        def __getattr__(self, name):
            raise AssertionError("Unsupported field must not be read: " + name)

    bpy = runtime()
    bpy.data.objects["Cube"].modifiers["Subdivision"] = Modifier()
    ctx = call(
        "get_modifier_values",
        bpy,
        object_name="Cube",
        modifier_name="Subdivision",
        properties=["target", "items", "custom", "large"],
    )["context"]
    assert all(row["status"] == "unsupported" and "value" not in row for row in ctx["properties"].values())


@pytest.mark.parametrize(
    "kind,value,extra",
    [
        ("FLOAT", float("nan"), {}),
        ("FLOAT", float("inf"), {}),
        ("INT", True, {}),
        ("STRING", "x" * 4097, {}),
        ("STRING", object(), {}),
        ("FLOAT", [1.0] * 33, {"is_array": True, "array_length": 3}),
        ("FLOAT", [1.0, float("nan"), 2.0], {"is_array": True, "array_length": 3}),
        ("ENUM", {str(n) for n in range(33)}, {"is_enum_flag": True}),
    ],
)
def test_unrepresentable_values_are_unavailable_not_truncated(kind, value, extra):
    bpy = runtime([property_info("setting", kind, **extra)], {"setting": value})
    result = call("get_modifier_values", bpy, object_name="Cube", modifier_name="Subdivision", properties=["setting"])
    row = result["context"]["properties"]["setting"]
    assert row["status"] == "unavailable"
    assert "value" not in row
    json.dumps(result, allow_nan=False)


def test_missing_property_is_unavailable_not_a_failed_entire_query():
    result = call("get_modifier_values", object_name="Cube", modifier_name="Subdivision", properties=["missing"])
    assert result["success"] is True
    assert result["context"]["properties"]["missing"]["reason"] == "property_not_found"


@pytest.mark.parametrize(
    "properties",
    [
        [],
        ["x"] * 33,
        ["x", "x"],
        ["_private"],
        ["rna_type"],
        ["x.y"],
        ["x[0]"],
        ["x()"],
        [1],
        ["a" * 129],
        "levels",
        {"levels": 1},
    ],
)
def test_property_selection_bounds_enforced_in_runtime(properties):
    assert (
        call("get_modifier_values", object_name="Cube", modifier_name="Subdivision", properties=properties)["success"]
        is False
    )


@pytest.mark.parametrize("name", ["", "  ", "x" * 257, "x\n", 123])
def test_object_and_modifier_name_bounds(name):
    assert (
        call("get_modifier_values", object_name=name, modifier_name="Subdivision", properties=["levels"])["success"]
        is False
    )
    assert (
        call("get_modifier_values", object_name="Cube", modifier_name=name, properties=["levels"])["success"] is False
    )


def test_missing_host_type_object_modifier_fail_explicitly():
    assert call("describe_rna_type", type_name="Missing")["success"] is False
    assert (
        call("get_modifier_values", object_name="Missing", modifier_name="Subdivision", properties=["levels"])[
            "success"
        ]
        is False
    )
    assert (
        call("get_modifier_values", object_name="Cube", modifier_name="Missing", properties=["levels"])["success"]
        is False
    )
    from dcc_mcp_blender import _rna_query

    with patch.dict("sys.modules", {"bpy": None}):
        assert _rna_query.search_rna_types()["success"] is False
        assert _rna_query.describe_rna_type("SubsurfModifier")["success"] is False
        assert _rna_query.get_modifier_values("Cube", "Subdivision", ["levels"])["success"] is False


def test_skill_schema_is_explicit_bounded_and_main_affinity():
    from dcc_mcp_core import validate_skill

    report = validate_skill(str(SKILL))
    assert not report.has_errors, report.issues
    tools = {tool["name"]: tool for tool in yaml.safe_load((SKILL / "tools.yaml").read_text(encoding="utf-8"))["tools"]}
    assert set(tools) == {"search_rna_types", "describe_rna_type", "get_modifier_values"}
    for tool in tools.values():
        assert tool["affinity"] == "main"
        assert tool["enforce_thread_affinity"] is True
        assert tool["read_only"] is True
        assert tool["annotations"]["read_only_hint"] is True
        assert tool["input_schema"]["additionalProperties"] is False
        assert tool["output_schema"]["required"] == ["success"]
        assert "read-only" in tool["tags"]
        assert (SKILL / tool["source_file"]).is_file()
    for name in ("search_rna_types", "describe_rna_type"):
        assert tools[name]["input_schema"]["properties"]["limit"]["maximum"] == 100
    selection = tools["get_modifier_values"]["input_schema"]["properties"]["properties"]
    assert selection["maxItems"] == 32
    assert selection["uniqueItems"] is True


def test_metadata_unicode_budget_advances_by_actual_count():
    enums = [SimpleNamespace(identifier="option" + str(n), name="树" * 140, description="树" * 170) for n in range(70)]
    props = [
        property_info("setting" + str(n), "ENUM", name="树" * 140, description="树" * 270, enum_items_static=enums)
        for n in range(100)
    ]
    bpy = runtime(props)
    seen = []
    offset = 0
    while offset is not None:
        result = call("describe_rna_type", bpy, type_name="SubsurfModifier", offset=offset, limit=100)
        assert len(json.dumps(result).encode("utf-8")) <= 32768
        ctx = result["context"]
        assert ctx["returned"] >= 1
        assert ctx["returned"] < 100
        if ctx["next_offset"] is not None:
            assert ctx["next_offset"] == offset + ctx["returned"]
        seen.extend(row["identifier"] for row in ctx["properties"])
        assert all(row["enum_truncated"] and row["text_truncated"] for row in ctx["properties"])
        offset = ctx["next_offset"]
    assert len(seen) == len(set(seen)) == 100


def test_search_unicode_budget_and_text_truncation():
    bpy = runtime()
    for n in range(100):
        name = "Type" + str(n)
        setattr(
            bpy.types,
            name,
            SimpleNamespace(bl_rna=SimpleNamespace(identifier=name, name="树" * 140, description="树" * 270)),
        )
    result = call("search_rna_types", bpy, query="Type", limit=100)
    ctx = result["context"]
    assert len(json.dumps(result).encode("utf-8")) <= 32768
    assert 0 < ctx["returned"] < 100
    assert ctx["next_offset"] == ctx["returned"]
    assert all(row["text_truncated"] for row in ctx["types"])


def test_value_budget_never_truncates_values_or_omits_requested_statuses():
    names = ["property" + "a" * 115 + str(n) for n in range(32)]
    values = {name: "树" * 4096 for name in names}
    result = call(
        "get_modifier_values",
        runtime([property_info(name, "STRING") for name in names], values),
        object_name="Cube",
        modifier_name="Subdivision",
        properties=names,
    )
    assert len(json.dumps(result).encode("utf-8")) <= 32768
    rows = result["context"]["properties"]
    assert set(rows) == set(names)
    for row in rows.values():
        assert row["status"] == "unavailable"
        assert row["reason"] == "response_budget_exceeded"
        assert "value" not in row


def test_enum_identifier_truncation_is_explicit():
    item = SimpleNamespace(identifier="X" * 129, name="Short", description="")
    row = call(
        "describe_rna_type",
        runtime([property_info("mode", "ENUM", enum_items_static=[item])]),
        type_name="SubsurfModifier",
    )["context"]["properties"][0]
    assert row["enum_items"][0]["text_truncated"] is True
    assert len(row["enum_items"][0]["identifier"]) == 128


def test_public_core_catalog_retains_rna_schema_and_affinity(monkeypatch):
    from dcc_mcp_core import create_skill_server

    monkeypatch.setenv("DCC_MCP_DISABLE_DEFAULT_SKILL_PATHS", "1")
    server = create_skill_server("blender", extra_paths=[str(SKILL.parent)])
    # Registration only; no host callback executes in this catalog test.
    executor = Mock(return_value="{}")
    server.set_in_process_executor(executor)
    names = server.load_skill("blender-rna")
    assert set(names) == {
        "blender_rna__search_rna_types",
        "blender_rna__describe_rna_type",
        "blender_rna__get_modifier_values",
    }
    info = server.get_skill_info("blender-rna")
    for tool in info["tools"]:
        assert tool["thread-affinity"] == "main"
        assert tool["enforce_thread_affinity"] is True
        assert tool["annotations"]["read_only_hint"] is True
        assert tool["output_schema"]["properties"]["context"]["properties"]["response_budget_bytes"]["const"] == 32768
        assert tool["input_schema"]["additionalProperties"] is False
    executor.assert_not_called()
