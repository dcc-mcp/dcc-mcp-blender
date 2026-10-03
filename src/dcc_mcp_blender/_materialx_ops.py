"""MaterialX (``.mtlx``) document import and export for Blender materials.

Blender ships no MaterialX document writer, and the MaterialX Python bindings
are not exposed inside Blender's interpreter, so both directions are built on
the standard library :mod:`xml.etree.ElementTree`. Export emits a
``standard_surface`` shader graph -- the same node Houdini's Karma MaterialX
builder produces -- so a document written here stays readable by hosts that
consume MaterialX. Import reads the three shader nodes that dominate real
documents: ``standard_surface``, ``open_pbr_surface`` and ``usd_preview_surface``.

Both directions are value-only: a socket driven by an upstream node keeps its
default value in the document and is reported under ``linked_inputs`` (export)
or ``connected_inputs`` (import) instead of being silently dropped.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Sequence, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._interchange_ops import _path
from dcc_mcp_blender._node_graph_ops import (
    _collection_get,
    _find_principled_node,
    _get_socket,
    _iter_collection,
    _set_socket_value,
    _socket_value,
)

MATERIALX_VERSION = "1.39"

_EXPORT_NODE_TYPE = "standard_surface"

# Principled BSDF socket -> MaterialX standard_surface input.
#
# Blender renamed several sockets between 3.x and 4.x, so two source sockets may
# target the same MaterialX input (``Sheen`` and ``Sheen Weight`` both map to
# ``sheen``). Only the first socket that actually exists on the node is exported,
# which keeps the document valid without version sniffing.
_PRINCIPLED_TO_STANDARD_SURFACE: List[Tuple[str, str, str]] = [
    ("Base Color", "base_color", "color3"),
    ("Metallic", "metalness", "float"),
    ("Roughness", "specular_roughness", "float"),
    ("IOR", "specular_IOR", "float"),
    ("Specular", "specular", "float"),
    ("Specular Tint", "specular_color", "color3"),
    ("Anisotropic", "specular_anisotropy", "float"),
    ("Anisotropic Rotation", "specular_rotation", "float"),
    ("Tangent", "tangent", "vector3"),
    ("Normal", "normal", "vector3"),
    ("Transmission Weight", "transmission", "float"),
    ("Transmission", "transmission", "float"),
    ("Alpha", "opacity", "color3"),
    ("Emission Strength", "emission", "float"),
    ("Emission Color", "emission_color", "color3"),
    ("Emission", "emission_color", "color3"),
    ("Coat Weight", "coat", "float"),
    ("Clearcoat", "coat", "float"),
    ("Coat Roughness", "coat_roughness", "float"),
    ("Clearcoat Roughness", "coat_roughness", "float"),
    ("Coat IOR", "coat_IOR", "float"),
    ("Coat Tint", "coat_color", "color3"),
    ("Sheen Weight", "sheen", "float"),
    ("Sheen", "sheen", "float"),
    ("Sheen Roughness", "sheen_roughness", "float"),
    ("Sheen Tint", "sheen_color", "color3"),
    ("Subsurface Weight", "subsurface", "float"),
    ("Subsurface", "subsurface", "float"),
    ("Subsurface Color", "subsurface_color", "color3"),
    ("Subsurface Radius", "subsurface_radius", "vector3"),
    ("Subsurface Scale", "subsurface_scale", "float"),
    ("Subsurface Anisotropy", "subsurface_anisotropy", "float"),
    ("Thin Film Thickness", "thin_film_thickness", "float"),
    ("Thin Film IOR", "thin_film_IOR", "float"),
]

# MaterialX shader input -> candidate Principled BSDF socket names.
#
# Tuples again carry the 3.x / 4.x rename pairs; the first socket that exists on
# the target node wins.
_STANDARD_SURFACE_TO_PRINCIPLED: List[Tuple[str, Tuple[str, ...], str]] = [
    ("base_color", ("Base Color",), "color"),
    ("metalness", ("Metallic",), "float"),
    ("specular_roughness", ("Roughness",), "float"),
    ("specular_IOR", ("IOR",), "float"),
    ("specular", ("Specular",), "float"),
    ("specular_color", ("Specular Tint",), "color"),
    ("specular_anisotropy", ("Anisotropic",), "float"),
    ("specular_rotation", ("Anisotropic Rotation",), "float"),
    ("tangent", ("Tangent",), "vector"),
    ("normal", ("Normal",), "vector"),
    ("transmission", ("Transmission Weight", "Transmission"), "float"),
    ("opacity", ("Alpha",), "float"),
    ("emission", ("Emission Strength",), "float"),
    ("emission_color", ("Emission Color", "Emission"), "color"),
    ("coat", ("Coat Weight", "Clearcoat"), "float"),
    ("coat_roughness", ("Coat Roughness", "Clearcoat Roughness"), "float"),
    ("coat_IOR", ("Coat IOR",), "float"),
    ("coat_color", ("Coat Tint",), "color"),
    ("sheen", ("Sheen Weight", "Sheen"), "float"),
    ("sheen_roughness", ("Sheen Roughness",), "float"),
    ("sheen_color", ("Sheen Tint",), "color"),
    ("subsurface", ("Subsurface Weight", "Subsurface"), "float"),
    ("subsurface_color", ("Subsurface Color",), "color"),
    ("subsurface_radius", ("Subsurface Radius",), "vector"),
    ("subsurface_scale", ("Subsurface Scale",), "float"),
    ("subsurface_anisotropy", ("Subsurface Anisotropy",), "float"),
    ("thin_film_thickness", ("Thin Film Thickness",), "float"),
    ("thin_film_IOR", ("Thin Film IOR",), "float"),
]

_OPEN_PBR_TO_PRINCIPLED: List[Tuple[str, Tuple[str, ...], str]] = [
    ("base_color", ("Base Color",), "color"),
    ("metalness", ("Metallic",), "float"),
    ("specular_roughness", ("Roughness",), "float"),
    ("specular_ior", ("IOR",), "float"),
    ("specular_color", ("Specular Tint",), "color"),
    ("specular_anisotropy", ("Anisotropic",), "float"),
    ("specular_rotation", ("Anisotropic Rotation",), "float"),
    ("transmission_weight", ("Transmission Weight", "Transmission"), "float"),
    ("emission_luminance", ("Emission Strength",), "float"),
    ("emission_color", ("Emission Color", "Emission"), "color"),
    ("coat_weight", ("Coat Weight", "Clearcoat"), "float"),
    ("coat_roughness", ("Coat Roughness", "Clearcoat Roughness"), "float"),
    ("coat_ior", ("Coat IOR",), "float"),
    ("coat_color", ("Coat Tint",), "color"),
    ("opacity", ("Alpha",), "float"),
    ("normal", ("Normal",), "vector"),
    ("tangent", ("Tangent",), "vector"),
    ("subsurface_weight", ("Subsurface Weight", "Subsurface"), "float"),
    ("subsurface_radius", ("Subsurface Radius",), "vector"),
    ("subsurface_scale", ("Subsurface Scale",), "float"),
    ("thin_film_thickness", ("Thin Film Thickness",), "float"),
    ("thin_film_ior", ("Thin Film IOR",), "float"),
]

_USD_PREVIEW_TO_PRINCIPLED: List[Tuple[str, Tuple[str, ...], str]] = [
    ("diffuseColor", ("Base Color",), "color"),
    ("emissiveColor", ("Emission Color", "Emission"), "color"),
    ("specularColor", ("Specular Tint",), "color"),
    ("metallic", ("Metallic",), "float"),
    ("roughness", ("Roughness",), "float"),
    ("clearcoat", ("Coat Weight", "Clearcoat"), "float"),
    ("clearcoatRoughness", ("Coat Roughness", "Clearcoat Roughness"), "float"),
    ("opacity", ("Alpha",), "float"),
    ("ior", ("IOR",), "float"),
    ("normal", ("Normal",), "vector"),
]

_IMPORT_MAPS: Dict[str, List[Tuple[str, Tuple[str, ...], str]]] = {
    "standard_surface": _STANDARD_SURFACE_TO_PRINCIPLED,
    "open_pbr_surface": _OPEN_PBR_TO_PRINCIPLED,
    "usd_preview_surface": _USD_PREVIEW_TO_PRINCIPLED,
}

_MATERIAL_TAGS = frozenset({"surfacematerial", "material"})


def _local_tag(tag: Any) -> str:
    text = str(tag)
    if text.startswith("{") and "}" in text:
        return text.split("}", 1)[1]
    return text


def _to_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce(value: Any, kind: str) -> Optional[Any]:
    """Normalise a socket value or parsed token list onto ``kind``.

    Returns ``None`` when no component is numeric, so callers can report the
    input as unsupported instead of writing ``nan`` into a document.
    """
    raw = list(value) if isinstance(value, (list, tuple)) else [value]
    numbers = [number for number in (_to_float(item) for item in raw) if number is not None]
    if not numbers:
        return None
    if kind == "float":
        return numbers[0]
    if len(numbers) == 1:
        numbers = [numbers[0]] * 3
    return numbers[:3]


def _format_value(value: Any, kind: str) -> str:
    if kind == "float":
        return "{:.6g}".format(float(value))
    return ", ".join("{:.6g}".format(float(component)) for component in value)


def _parse_value(text: str, kind: str) -> Optional[Any]:
    tokens = str(text).replace(",", " ").split()
    return _coerce(tokens, kind)


def _sanitize_node_name(name: str, used: set) -> str:
    """Return a MaterialX-legal node name unique within ``used``.

    MaterialX identifiers are ``[A-Za-z_][A-Za-z0-9_]*``; Blender material names
    routinely contain spaces, dots and leading digits, which would produce a
    document no host can load.
    """
    cleaned = []
    for char in str(name or "material"):
        cleaned.append(char if (char.isascii() and (char.isalnum() or char == "_")) else "_")
    candidate = "".join(cleaned)
    if not candidate or not (candidate[0].isalpha() or candidate[0] == "_"):
        candidate = "M_" + candidate
    unique = candidate
    index = 2
    while unique in used:
        unique = "{}_{}".format(candidate, index)
        index += 1
    used.add(unique)
    return unique


def _indent(element: ET.Element, level: int = 0) -> None:
    """Pretty-print in place.

    :func:`xml.etree.ElementTree.indent` is Python 3.9+, and this package still
    supports the 3.7 lane, so the walk is done here.
    """
    pad = "\n" + "  " * level
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = pad + "  "
        for child in children:
            _indent(child, level + 1)
        if not children[-1].tail or not children[-1].tail.strip():
            children[-1].tail = pad
    elif level and (not element.tail or not element.tail.strip()):
        element.tail = pad


def _mtlx_path(path: str, **kwargs: Any) -> Tuple[Optional[Any], Optional[dict]]:
    """Resolve ``path`` and pin the MaterialX extension.

    A bare path gets ``.mtlx`` appended; an explicit foreign extension is an
    error rather than a silent rewrite, because MaterialX consumers key off the
    suffix.
    """
    target, error = _path(path, **kwargs)
    if error:
        return None, error
    if target.suffix:
        if target.suffix.lower() != ".mtlx":
            return None, skill_error(
                f"Unsupported MaterialX extension '{target.suffix}'",
                "MaterialX documents must use the .mtlx extension.",
            )
        return target, None
    return target.with_suffix(".mtlx"), None


def _requested_names(material_names: Sequence[str] | None) -> Tuple[List[str], Optional[dict]]:
    if material_names is None:
        return [], None
    if isinstance(material_names, str) or not material_names:
        return [], skill_error(
            "Invalid material_names", "material_names must be a non-empty list of material names when provided."
        )
    return [str(name) for name in material_names], None


def _shader_inputs(element: ET.Element) -> Tuple[Dict[str, str], List[str]]:
    """Split a shader element's inputs into literal values and connections."""
    values: Dict[str, str] = {}
    connected: List[str] = []
    for child in list(element):
        if _local_tag(child.tag) != "input":
            continue
        name = child.get("name")
        if not name:
            continue
        if child.get("nodename") or child.get("nodegraph") or child.get("outputstring"):
            connected.append(name)
            continue
        value = child.get("value")
        if value is not None:
            values[name] = value
    return values, connected


def _collect_material_elements(root: ET.Element) -> Tuple[List[ET.Element], Dict[str, ET.Element]]:
    """Return (material elements, shader nodes indexed by name)."""
    nodes: Dict[str, ET.Element] = {}
    materials: List[ET.Element] = []
    for element in root.iter():
        name = element.get("name")
        if name:
            nodes.setdefault(name, element)
        if _local_tag(element.tag) in _MATERIAL_TAGS:
            materials.append(element)
    return materials, nodes


def _resolve_shader(material: ET.Element, nodes: Dict[str, ET.Element]) -> Optional[ET.Element]:
    """Find the shader node a material element renders with."""
    for child in list(material):
        tag = _local_tag(child.tag)
        if tag == "input":
            node_name = child.get("nodename")
            if node_name:
                shader = nodes.get(node_name)
                if shader is None:
                    shader = nodes.get(node_name.split("/")[-1])
                if shader is not None:
                    return shader
        elif tag == "shaderref":
            for candidate in (child.get("name"), child.get("node")):
                if not candidate:
                    continue
                shader = nodes.get(candidate)
                if shader is not None and _local_tag(shader.tag) in _IMPORT_MAPS:
                    return shader
    return None


def _fallback_shaders(root: ET.Element) -> List[ET.Element]:
    """Shader nodes to import when the document declares no material element."""
    return [element for element in root.iter() if _local_tag(element.tag) in _IMPORT_MAPS]


def export_materialx(
    path: str,
    material_names: Sequence[str] | None = None,
    overwrite: bool = True,
) -> dict:
    """Export Principled BSDF materials to a MaterialX ``.mtlx`` document.

    Args:
        path: Destination file path.
        material_names: Materials to export; every material in the file when omitted.
        overwrite: Overwrite an existing file. Fails when ``False`` and the file exists.

    Returns:
        ActionResultModel dict.
    """
    target, error = _mtlx_path(path, create_parent=True)
    if error:
        return error
    requested, error = _requested_names(material_names)
    if error:
        return error
    if target.exists() and not overwrite:
        return skill_error(f"File already exists: {target}", "Pass overwrite=true to replace it.")

    try:
        import bpy

        materials = []
        missing = []
        for name in requested:
            material = _collection_get(bpy.data.materials, name)
            if material is None:
                missing.append(name)
            else:
                materials.append(material)
        if missing:
            return skill_error("Material not found", f"Missing material(s): {', '.join(missing)}")
        if not requested:
            materials = list(_iter_collection(bpy.data.materials))
        if not materials:
            return skill_error("No materials to export", "The scene has no materials.")

        root = ET.Element("materialx", {"version": MATERIALX_VERSION, "colorspace": "lin_rec709"})
        used_names: set = set()
        exported: List[dict] = []
        skipped: List[dict] = []

        for material in materials:
            node_name = getattr(material, "name", None) or "material"
            if not getattr(material, "use_nodes", False) or getattr(material, "node_tree", None) is None:
                skipped.append({"material": node_name, "reason": "material does not use nodes"})
                continue
            bsdf = _find_principled_node(material.node_tree.nodes)
            if bsdf is None:
                skipped.append({"material": node_name, "reason": "no Principled BSDF node"})
                continue

            values: Dict[str, Any] = {}
            linked: List[str] = []
            seen_targets: set = set()
            for socket_name, mtlx_name, mtlx_type in _PRINCIPLED_TO_STANDARD_SURFACE:
                if mtlx_name in seen_targets:
                    continue
                socket = _get_socket(bsdf.inputs, socket_name)
                if socket is None:
                    continue
                value = _coerce(_socket_value(socket), mtlx_type)
                if value is None:
                    continue
                values[mtlx_name] = (value, mtlx_type)
                seen_targets.add(mtlx_name)
                if getattr(socket, "is_linked", False):
                    linked.append(socket_name)

            if not values:
                skipped.append({"material": node_name, "reason": "no mappable Principled BSDF inputs"})
                continue
            # standard_surface gates emission behind a weight that defaults to 0,
            # so an emission colour without a strength would render as black.
            if "emission_color" in values and "emission" not in values:
                values["emission"] = (1.0, "float")

            shader_node = _sanitize_node_name("{}_shader".format(node_name), used_names)
            material_node = _sanitize_node_name(node_name, used_names)
            shader = ET.SubElement(root, _EXPORT_NODE_TYPE, {"name": shader_node, "type": "surfaceshader"})
            for mtlx_name in sorted(values):
                value, mtlx_type = values[mtlx_name]
                ET.SubElement(
                    shader, "input", {"name": mtlx_name, "type": mtlx_type, "value": _format_value(value, mtlx_type)}
                )
            surface = ET.SubElement(root, "surfacematerial", {"name": material_node, "type": "material"})
            ET.SubElement(
                surface,
                "input",
                {"name": "surfaceshader", "type": "surfaceshader", "nodename": shader_node},
            )
            exported.append(
                {
                    "material": node_name,
                    "node": material_node,
                    "shader": shader_node,
                    "inputs": sorted(values),
                    "linked_inputs": linked,
                }
            )

        if not exported:
            return skill_error(
                "No Principled BSDF material could be exported",
                "; ".join(f"{item['material']}: {item['reason']}" for item in skipped),
                skipped=skipped,
            )

        _indent(root)
        ET.ElementTree(root).write(str(target), encoding="utf-8", xml_declaration=True)

        warnings = ["{}: {}".format(item["material"], item["reason"]) for item in skipped]
        warnings.extend(
            "{}: socket '{}' is driven by a node; its default value was exported".format(item["material"], socket)
            for item in exported
            for socket in item["linked_inputs"]
        )
        return skill_success(
            "Exported {} material(s) to {}".format(len(exported), target.name),
            path=str(target),
            node_type=_EXPORT_NODE_TYPE,
            materialx_version=MATERIALX_VERSION,
            material_count=len(exported),
            materials=exported,
            bytes=target.stat().st_size,
            skipped=skipped,
            warnings=warnings,
            prompt="Textures and other node graphs are not baked; only Principled BSDF socket values are written.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to export MaterialX to {target}")


def import_materialx(
    path: str,
    material_names: Sequence[str] | None = None,
    reuse_existing: bool = True,
) -> dict:
    """Import a MaterialX ``.mtlx`` document into Blender materials.

    Args:
        path: Source ``.mtlx`` file.
        material_names: Materials to import; every material in the document when omitted.
        reuse_existing: Update an existing material of the same name instead of
            letting Blender create ``Name.001``.

    Returns:
        ActionResultModel dict.
    """
    source, error = _mtlx_path(path, must_exist=True)
    if error:
        return error
    requested, error = _requested_names(material_names)
    if error:
        return error

    try:
        root = ET.parse(str(source)).getroot()
    except ET.ParseError as exc:
        return skill_error(f"Invalid MaterialX document: {source.name}", str(exc))
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to read MaterialX document: {source}")

    materials, nodes = _collect_material_elements(root)
    unsupported: List[dict] = []
    if materials:
        entries = []
        for material in materials:
            shader = _resolve_shader(material, nodes)
            if shader is None:
                unsupported.append({"material": material.get("name") or "", "reason": "no supported shader node"})
                continue
            entries.append((material.get("name") or "", shader))
    else:
        entries = [(element.get("name") or "", element) for element in _fallback_shaders(root)]

    if not entries:
        detail = "; ".join(f"{item['material']}: {item['reason']}" for item in unsupported) or (
            "The document contains no standard_surface, open_pbr_surface or usd_preview_surface node."
        )
        return skill_error(f"No MaterialX material found in {source.name}", detail)

    if requested:
        wanted = set(requested)
        found = {name for name, _ in entries}
        missing = sorted(wanted - found)
        if missing:
            return skill_error(
                "Material not found",
                "Missing MaterialX material(s): {}".format(", ".join(missing)),
                available=sorted(found),
            )
        entries = [entry for entry in entries if entry[0] in wanted]

    try:
        import bpy

        imported: List[dict] = []
        for name, shader in entries:
            shader_type = _local_tag(shader.tag)
            mapping = _IMPORT_MAPS.get(shader_type)
            if mapping is None:
                unsupported.append({"material": name, "reason": f"unsupported shader node '{shader_type}'"})
                continue
            values, connected = _shader_inputs(shader)

            material = _collection_get(bpy.data.materials, name) if reuse_existing else None
            action = "updated"
            if material is None:
                material = bpy.data.materials.new(name)
                action = "created"
            material.use_nodes = True
            node_tree = getattr(material, "node_tree", None)
            if node_tree is None:
                unsupported.append({"material": name, "reason": "material has no node tree"})
                continue
            bsdf = _find_principled_node(node_tree.nodes)
            if bsdf is None:
                unsupported.append({"material": name, "reason": "no Principled BSDF node"})
                continue

            applied: Dict[str, Any] = {}
            unmapped: List[str] = []
            known_inputs = {entry[0] for entry in mapping}
            for mtlx_name, socket_names, kind in mapping:
                if mtlx_name not in values:
                    continue
                value = _parse_value(values[mtlx_name], kind)
                if value is None:
                    unmapped.append(mtlx_name)
                    continue
                socket = None
                for socket_name in socket_names:
                    socket = _get_socket(bsdf.inputs, socket_name)
                    if socket is not None:
                        break
                if socket is None:
                    unmapped.append(mtlx_name)
                    continue
                try:
                    applied[getattr(socket, "name", socket_names[0])] = _set_socket_value(socket, value)
                except ValueError:
                    unmapped.append(mtlx_name)
            for mtlx_name in values:
                if mtlx_name not in known_inputs:
                    unmapped.append(mtlx_name)

            imported.append(
                {
                    "material": getattr(material, "name", name),
                    "source_node": shader_type,
                    "action": action,
                    "applied": applied,
                    "unmapped_inputs": sorted(set(unmapped)),
                    "connected_inputs": sorted(set(connected)),
                }
            )

        if not imported:
            detail = "; ".join(f"{item['material']}: {item['reason']}" for item in unsupported)
            return skill_error(f"No MaterialX material could be imported from {source.name}", detail)

        warnings = ["{}: {}".format(item["material"], item["reason"]) for item in unsupported]
        for item in imported:
            for mtlx_name in item["connected_inputs"]:
                warnings.append(
                    "{}: input '{}' is a node connection and was not imported".format(item["material"], mtlx_name)
                )
        return skill_success(
            "Imported {} material(s) from {}".format(len(imported), source.name),
            path=str(source),
            materialx_version=root.get("version"),
            material_count=len(imported),
            materials=imported,
            unsupported=unsupported,
            warnings=warnings,
            prompt="Use assign_material to bind an imported material to an object.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to import MaterialX from {source}")
