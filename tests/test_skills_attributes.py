"""Unit tests for blender-attributes skill scripts (bpy mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


def _make_obj(name="Cube"):
    obj = MagicMock()
    obj.name = name
    obj.type = "MESH"
    obj._props = {}
    obj.keys = lambda: list(obj._props.keys())
    obj.__contains__ = lambda self, k: k in self._props
    obj.__getitem__ = lambda self, k: self._props[k]
    obj.__setitem__ = lambda self, k, v: self._props.__setitem__(k, v)
    obj.__delitem__ = lambda self, k: self._props.__delitem__(k)
    obj.get = lambda k, default=None: obj._props.get(k, default)
    obj.id_properties_ui = MagicMock(
        return_value=SimpleNamespace(as_dict=lambda: {"min": 0, "max": 1}, update=lambda **kw: None)
    )
    return obj


def test_list_attributes_empty():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call("blender-attributes/scripts/list_attributes.py", bpy, object_name="Cube")
    assert result["success"] is True
    assert result["context"]["count"] == 0


def test_list_attributes_with_props():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    obj._props["health"] = 100
    obj._props["name_tag"] = "hero"
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call("blender-attributes/scripts/list_attributes.py", bpy, object_name="Cube")
    assert result["success"] is True
    assert result["context"]["count"] == 2


def test_get_attribute():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    obj._props["health"] = 100
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call(
        "blender-attributes/scripts/get_attribute.py", bpy, object_name="Cube", attribute_name="health"
    )
    assert result["success"] is True
    assert result["context"]["value"] == 100


def test_get_attribute_not_found():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call(
        "blender-attributes/scripts/get_attribute.py", bpy, object_name="Cube", attribute_name="nonexistent"
    )
    assert result["success"] is False


def test_set_attribute_string():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call(
        "blender-attributes/scripts/set_attribute.py", bpy, object_name="Cube", attribute_name="tag", value="hero"
    )
    assert result["success"] is True
    assert obj._props["tag"] == "hero"


def test_set_attribute_number():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call(
        "blender-attributes/scripts/set_attribute.py", bpy, object_name="Cube", attribute_name="count", value=42
    )
    assert result["success"] is True
    assert obj._props["count"] == 42


def test_delete_attribute():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    obj._props["temp"] = "value"
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call(
        "blender-attributes/scripts/delete_attribute.py", bpy, object_name="Cube", attribute_name="temp"
    )
    assert result["success"] is True
    assert "temp" not in obj._props


def test_delete_attribute_not_found():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call(
        "blender-attributes/scripts/delete_attribute.py", bpy, object_name="Cube", attribute_name="nonexistent"
    )
    assert result["success"] is False


def test_rename_attribute():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    obj._props["old_name"] = 42
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call(
        "blender-attributes/scripts/rename_attribute.py",
        bpy,
        object_name="Cube",
        old_name="old_name",
        new_name="new_name",
    )
    assert result["success"] is True
    assert "old_name" not in obj._props
    assert obj._props["new_name"] == 42


def test_rename_attribute_not_found():
    bpy = make_mock_bpy()
    obj = _make_obj("Cube")
    bpy.data.objects.get = MagicMock(return_value=obj)

    result = load_and_call(
        "blender-attributes/scripts/rename_attribute.py",
        bpy,
        object_name="Cube",
        old_name="nonexistent",
        new_name="newname",
    )
    assert result["success"] is False


def test_list_attributes_object_not_found():
    bpy = make_mock_bpy()
    bpy.data.objects.get = MagicMock(return_value=None)

    result = load_and_call("blender-attributes/scripts/list_attributes.py", bpy, object_name="Missing")
    assert result["success"] is False


def test_tools_yaml_declares_modern_contracts():
    from pathlib import Path

    import yaml

    doc = yaml.safe_load(Path("src/dcc_mcp_blender/skills/blender-attributes/tools.yaml").read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {"list_attributes", "get_attribute", "set_attribute", "delete_attribute", "rename_attribute"}.issubset(tools)
    for tool in tools.values():
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert "annotations" in tool
