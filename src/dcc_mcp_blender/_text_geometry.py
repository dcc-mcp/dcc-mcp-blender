"""Bounded editable native text using Blender's built-in font, without file IO."""

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success
from dcc_mcp_core.skills_helper import check_dcc_cancelled

from ._data_geometry import _cleanup_owned, _name, _number


def validate_text(name, text, size, extrude, align_x):
    _name(name)
    if (
        not isinstance(text, str)
        or not 1 <= len(text) <= 160
        or text.count("\n") > 2
        or any(c != "\n" and not 32 <= ord(c) <= 126 for c in text)
    ):
        raise ValueError("Use 1–160 printable ASCII characters, at most three lines")
    _number(size, 0.001, 10)
    _number(extrude, 0, 0.1)
    if align_x not in {"LEFT", "CENTER", "RIGHT"}:
        raise ValueError("Text alignment must be LEFT, CENTER or RIGHT")


def _assert_builtin_fonts(data):
    for slot in ("font", "font_bold", "font_italic", "font_bold_italic"):
        font = getattr(data, slot, None)
        if font is None and slot != "font":
            continue
        if font is None or font.filepath != "<builtin>" or font.library is not None:
            raise ValueError("Inspect only bounded text using built-in fonts in every style slot")


def _payload(obj):
    data = obj.data
    validate_text(obj.name, data.body, 0.2, 0.0, data.align_x)
    _number(float(data.size), 0.001 - 1e-8, 10 + 1e-6)
    _number(float(data.extrude), 0, 0.1 + 1e-8)
    _assert_builtin_fonts(data)
    return {
        "object_name": obj.name,
        "type": obj.type,
        "text": data.body,
        "size": float(data.size),
        "extrude": float(data.extrude),
        "align_x": data.align_x,
        "font": data.font.name,
        "location": list(obj.location),
        "dimensions": list(obj.dimensions),
        "materials": [m.name if m else None for m in data.materials],
    }


def create_text(name, text, size=0.2, extrude=0.0, align_x="LEFT", material_name=None):
    """Create one editable native font curve and verify its body and formatting."""
    obj = data = None
    try:
        validate_text(name, text, size, extrude, align_x)
        if material_name is not None:
            _name(material_name)
        import bpy

        if bpy.data.objects.get(name) is not None or bpy.data.curves.get(name) is not None:
            return skill_error("Name already exists", "Use a fresh object/data name")
        material = bpy.data.materials.get(material_name) if material_name else None
        if material_name and material is None:
            return skill_error("Material does not exist", "Create or select an existing material first")
        check_dcc_cancelled()
        data = bpy.data.curves.new(name, type="FONT")
        data.body = text
        data.size = size
        data.extrude = extrude
        data.align_x = align_x
        if material is not None:
            data.materials.append(material)
        if data.body != text or abs(data.size - size) > 1e-6 or abs(data.extrude - extrude) > 1e-6:
            raise RuntimeError("Native text readback differs from requested formatting")
        if data.align_x != align_x:
            raise RuntimeError("Native text alignment did not match the request")
        _assert_builtin_fonts(data)
        check_dcc_cancelled()
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return skill_success(
            "Editable native text created and read back",
            verified=True,
            postcondition={"method": "native_font_readback"},
            **_payload(obj),
        )
    except Exception as exc:
        try:
            if data is not None:
                _cleanup_owned(bpy, obj, data, bpy.data.curves)
        except Exception:
            return skill_exception(exc, message="Text creation failed; inspect owned data cleanup")
        return skill_exception(exc, message="Text creation rejected without changing an existing object")


def inspect_text(name):
    """Read a bounded built-in-font object without modifying its data."""
    try:
        _name(name)
        import bpy

        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "FONT":
            return skill_error("Text object not found", "Select an existing native FONT object")
        return skill_success("Native text inspected", **_payload(obj))
    except Exception as exc:
        return skill_exception(exc, message="Text inspection rejected without mutation")
