"""Typed guide-curve grooming helpers for imported character meshes.

An external asset-generation skill owns image or multiview generation. This
module owns the Blender-side handoff after an asset has been imported: it
attaches deterministic guide curves to a source mesh, creates a simple hair
material, and exposes safe style edits with readback metadata.
"""

from __future__ import annotations

import json
import math
import random
from typing import Any, Sequence, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_GROOM_MARKER = "dcc_mcp_groom"
_GROOM_VERSION = 1
_GROOM_SOURCE_KEY = "dcc_mcp_groom_source_object"
_GROOM_PARAMETERS_KEY = "dcc_mcp_groom_parameters"
_GROOM_STYLE_KEY = "dcc_mcp_groom_style"
_GROOM_SHAPE_KEY = "dcc_mcp_groom_shape"
_DEFAULT_MATERIAL_NAME = "DCC MCP Groom Hair"
_DEFAULT_COLOR = (0.035, 0.012, 0.006, 1.0)
_UP = (0.0, 0.0, 1.0)


def _vector(value: Sequence[float]) -> Tuple[float, float, float] | None:
    if isinstance(value, (str, bytes)):
        return None
    try:
        if len(value) != 3:  # type: ignore[arg-type]
            return None
        result = (float(value[0]), float(value[1]), float(value[2]))
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(component) for component in result):
        return None
    return result


def _add(left: Sequence[float], right: Sequence[float]) -> Tuple[float, float, float]:
    return tuple(float(left[index]) + float(right[index]) for index in range(3))  # type: ignore[return-value]


def _sub(left: Sequence[float], right: Sequence[float]) -> Tuple[float, float, float]:
    return tuple(float(left[index]) - float(right[index]) for index in range(3))  # type: ignore[return-value]


def _scale(value: Sequence[float], factor: float) -> Tuple[float, float, float]:
    return tuple(float(component) * factor for component in value)  # type: ignore[return-value]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(left[index]) * float(right[index]) for index in range(3))


def _cross(left: Sequence[float], right: Sequence[float]) -> Tuple[float, float, float]:
    return (
        float(left[1]) * float(right[2]) - float(left[2]) * float(right[1]),
        float(left[2]) * float(right[0]) - float(left[0]) * float(right[2]),
        float(left[0]) * float(right[1]) - float(left[1]) * float(right[0]),
    )


def _normalize(value: Sequence[float], fallback: Sequence[float] = _UP) -> Tuple[float, float, float]:
    length = math.sqrt(_dot(value, value))
    if length <= 1e-8:
        return tuple(float(component) for component in fallback)  # type: ignore[return-value]
    return _scale(value, 1.0 / length)


def _transform_point(obj: Any, value: Sequence[float]) -> Tuple[float, float, float]:
    matrix = getattr(obj, "matrix_world", None)
    if matrix is not None:
        try:
            from mathutils import Vector

            transformed = matrix @ Vector(value)
            return (float(transformed[0]), float(transformed[1]), float(transformed[2]))
        except Exception:
            pass
    return (float(value[0]), float(value[1]), float(value[2]))


def _transform_normal(obj: Any, value: Sequence[float]) -> Tuple[float, float, float]:
    matrix = getattr(obj, "matrix_world", None)
    if matrix is not None:
        try:
            from mathutils import Vector

            transformed = matrix.to_3x3() @ Vector(value)
            return _normalize(transformed)
        except Exception:
            pass
    return _normalize(value)


def _custom_get(target: Any, key: str, default: Any = None) -> Any:
    getter = getattr(target, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except Exception:
            return default
    return default


def _custom_set(target: Any, key: str, value: Any) -> None:
    try:
        target[key] = value
    except Exception:
        setattr(target, key, value)


def _json_value(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return default
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _validate_parameters(
    guide_count: int,
    segments: int,
    length: float,
    width: float,
    normal_weight: float,
    curl: float,
    direction_bias: Sequence[float],
    hair_color: Sequence[float],
    root_height_min: float,
    root_height_max: float,
) -> dict | None:
    if isinstance(guide_count, bool) or not isinstance(guide_count, int) or not 1 <= guide_count <= 20000:
        return skill_error("Invalid guide_count", "guide_count must be an integer between 1 and 20000.")
    if isinstance(segments, bool) or not isinstance(segments, int) or not 2 <= segments <= 32:
        return skill_error("Invalid segments", "segments must be an integer between 2 and 32.")
    try:
        length_value = float(length)
        width_value = float(width)
        normal_weight_value = float(normal_weight)
        curl_value = float(curl)
    except (TypeError, ValueError):
        return skill_error("Invalid groom parameters", "length, width, normal_weight, and curl must be numeric.")
    if not all(math.isfinite(value) for value in (length_value, width_value, normal_weight_value, curl_value)):
        return skill_error("Invalid groom parameters", "length, width, normal_weight, and curl must be finite.")
    if not 0.000001 < length_value <= 100.0:
        return skill_error("Invalid length", "length must be greater than 0 and no more than 100 Blender units.")
    if not 0.000001 < width_value <= 1.0:
        return skill_error("Invalid width", "width must be greater than 0 and no more than 1 Blender unit.")
    if not 0.0 <= normal_weight_value <= 1.0:
        return skill_error("Invalid normal_weight", "normal_weight must be between 0 and 1.")
    if not 0.0 <= curl_value <= 1.0:
        return skill_error("Invalid curl", "curl must be between 0 and 1.")
    try:
        root_height_min_value = float(root_height_min)
        root_height_max_value = float(root_height_max)
    except (TypeError, ValueError):
        return skill_error("Invalid root height", "root_height_min and root_height_max must be numeric.")
    if (
        not math.isfinite(root_height_min_value)
        or not math.isfinite(root_height_max_value)
        or not 0.0 <= root_height_min_value < root_height_max_value <= 1.0
    ):
        return skill_error("Invalid root height", "Root height bounds must satisfy 0 <= min < max <= 1.")
    if _vector(direction_bias) is None:
        return skill_error("Invalid direction_bias", "direction_bias must contain three finite numbers.")
    if isinstance(hair_color, (str, bytes)) or len(hair_color) not in (3, 4):
        return skill_error("Invalid hair_color", "hair_color must contain three or four values.")
    try:
        color = [float(value) for value in hair_color]
    except (TypeError, ValueError):
        return skill_error("Invalid hair_color", "hair_color must contain numeric values.")
    if not all(0.0 <= value <= 1.0 for value in color):
        return skill_error("Invalid hair_color", "hair_color values must be between 0 and 1.")
    return None


def _ensure_collection(bpy: Any, collection_name: str | None) -> Any:
    if collection_name:
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(collection)
        return collection
    context_collection = getattr(bpy.context, "collection", None)
    if context_collection is not None:
        return context_collection
    return bpy.context.scene.collection


def _ensure_material(
    bpy: Any,
    material_name: str,
    color: Sequence[float] | None = None,
    roughness: float | None = None,
) -> Any:
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(name=material_name)
    material.use_nodes = True
    node_tree = getattr(material, "node_tree", None)
    nodes = getattr(node_tree, "nodes", None)
    bsdf = nodes.get("Principled BSDF") if nodes is not None else None
    rgba = list(color or _DEFAULT_COLOR)
    if len(rgba) == 3:
        rgba.append(1.0)
    if bsdf is not None:
        inputs = getattr(bsdf, "inputs", {})
        base_color = inputs.get("Base Color")
        if base_color is not None:
            base_color.default_value = rgba
        if roughness is not None:
            roughness_input = inputs.get("Roughness")
            if roughness_input is not None:
                roughness_input.default_value = float(roughness)
    if hasattr(material, "diffuse_color"):
        material.diffuse_color = rgba
    return material


def _remove_existing_groom(bpy: Any, object_name: str) -> None:
    existing = bpy.data.objects.get(object_name)
    if existing is None:
        return
    if _custom_get(existing, _GROOM_MARKER) != _GROOM_VERSION:
        return
    data = getattr(existing, "data", None)
    bpy.data.objects.remove(existing, do_unlink=True)
    if data is not None and getattr(data, "users", 1) == 0:
        try:
            bpy.data.curves.remove(data)
        except Exception:
            pass


def _point_count(obj: Any) -> int:
    curve_data = getattr(obj, "data", None)
    splines = getattr(curve_data, "splines", [])
    return sum(len(getattr(spline, "points", [])) for spline in splines)


def _summary(obj: Any) -> dict:
    curve_data = getattr(obj, "data", None)
    splines = list(getattr(curve_data, "splines", []))
    return {
        "object_name": getattr(obj, "name", None),
        "object_type": getattr(obj, "type", None),
        "guide_count": len(splines),
        "point_count": _point_count(obj),
        "source_object": _custom_get(obj, _GROOM_SOURCE_KEY),
        "parameters": _json_value(_custom_get(obj, _GROOM_PARAMETERS_KEY, {}), {}),
        "style": _json_value(_custom_get(obj, _GROOM_STYLE_KEY, {}), {}),
        "shape": _json_value(_custom_get(obj, _GROOM_SHAPE_KEY, {}), {}),
        "hide_viewport": bool(getattr(obj, "hide_viewport", False)),
        "hide_render": bool(getattr(obj, "hide_render", False)),
        "material_names": [getattr(material, "name", None) for material in getattr(curve_data, "materials", [])],
    }


def _generated_groom(bpy: Any, object_name: str) -> tuple[Any | None, dict | None]:
    """Return a generated groom object or a consistent skill error."""
    groom = bpy.data.objects.get(object_name)
    if groom is None:
        return None, skill_error(f"Object not found: {object_name}", "Pass a generated groom object name.")
    if _custom_get(groom, _GROOM_MARKER) != _GROOM_VERSION or getattr(groom, "type", None) != "CURVE":
        return None, skill_error(
            f"Object is not a generated groom: {object_name}",
            "This operation is restricted to blender-groom output.",
        )
    return groom, None


def _copy_curve_data(bpy: Any, source_data: Any, name: str) -> Any:
    """Copy curve data, with a small fallback for Blender test doubles."""
    copier = getattr(source_data, "copy", None)
    if callable(copier):
        copied = copier()
        copied.name = name
        return copied

    copied = bpy.data.curves.new(name=name, type="CURVE")
    for attribute in ("dimensions", "resolution_u", "bevel_depth", "bevel_resolution"):
        if hasattr(source_data, attribute):
            setattr(copied, attribute, getattr(source_data, attribute))
    for source_spline in getattr(source_data, "splines", []):
        spline_type = getattr(source_spline, "type", "NURBS")
        target_spline = copied.splines.new(spline_type)
        source_points = list(getattr(source_spline, "points", []))
        if source_points:
            target_spline.points.add(len(source_points) - 1)
        for source_point, target_point in zip(source_points, getattr(target_spline, "points", [])):
            target_point.co = tuple(source_point.co)
            if hasattr(source_point, "radius"):
                target_point.radius = source_point.radius
        for attribute in ("order_u", "use_endpoint_u", "use_cyclic_u", "resolution_u"):
            if hasattr(source_spline, attribute) and hasattr(target_spline, attribute):
                setattr(target_spline, attribute, getattr(source_spline, attribute))
    for material in getattr(source_data, "materials", []):
        copied.materials.append(material)
    return copied


def _select_root_vertices(vertices: list[Any], root_height_min: float, root_height_max: float) -> list[Any]:
    coordinates = [_vector(getattr(vertex, "co", (0.0, 0.0, 0.0))) for vertex in vertices]
    valid_coordinates = [coordinate for coordinate in coordinates if coordinate is not None]
    if not valid_coordinates:
        return vertices
    minimum = min(coordinate[2] for coordinate in valid_coordinates)
    maximum = max(coordinate[2] for coordinate in valid_coordinates)
    span = maximum - minimum
    if span <= 1e-8:
        return vertices
    selected = []
    for vertex, coordinate in zip(vertices, coordinates):
        if coordinate is None:
            continue
        normalized_height = (coordinate[2] - minimum) / span
        if root_height_min <= normalized_height <= root_height_max:
            selected.append(vertex)
    return selected or vertices


def create_groom_guides(
    scalp_object_name: str,
    groom_name: str = "Hair Groom",
    guide_count: int = 800,
    segments: int = 8,
    length: float = 0.15,
    width: float = 0.003,
    normal_weight: float = 0.85,
    direction_bias: Sequence[float] = _UP,
    curl: float = 0.15,
    seed: int = 0,
    collection_name: str | None = None,
    material_name: str = _DEFAULT_MATERIAL_NAME,
    hair_color: Sequence[float] = _DEFAULT_COLOR,
    roughness: float = 0.55,
    root_height_min: float = 0.2,
    root_height_max: float = 1.0,
    replace_existing: bool = False,
) -> dict:
    """Create deterministic guide curves attached to mesh vertices."""
    error = _validate_parameters(
        guide_count,
        segments,
        length,
        width,
        normal_weight,
        curl,
        direction_bias,
        hair_color,
        root_height_min,
        root_height_max,
    )
    if error:
        return error
    if not groom_name or not groom_name.strip():
        return skill_error("Invalid groom_name", "groom_name must be a non-empty string.")
    try:
        roughness_value = float(roughness)
    except (TypeError, ValueError):
        return skill_error("Invalid roughness", "roughness must be numeric.")
    if not math.isfinite(roughness_value) or not 0.0 <= roughness_value <= 1.0:
        return skill_error("Invalid roughness", "roughness must be between 0 and 1.")
    length_value = float(length)
    width_value = float(width)
    normal_weight_value = float(normal_weight)
    curl_value = float(curl)
    root_height_min_value = float(root_height_min)
    root_height_max_value = float(root_height_max)

    try:
        import bpy

        scalp = bpy.data.objects.get(scalp_object_name)
        if scalp is None:
            return skill_error(f"Object not found: {scalp_object_name}", "scalp_object_name must name a mesh object.")
        if getattr(scalp, "type", None) != "MESH":
            return skill_error(
                f"Object is not a mesh: {scalp_object_name}",
                "Guide roots require a mesh object with vertices and normals.",
            )
        vertices = list(getattr(getattr(scalp, "data", None), "vertices", []))
        if not vertices:
            return skill_error(
                f"Mesh has no vertices: {scalp_object_name}", "Cannot attach groom guides to an empty mesh."
            )
        root_vertices = _select_root_vertices(vertices, root_height_min_value, root_height_max_value)
        if bpy.data.objects.get(groom_name) is not None:
            if not replace_existing:
                return skill_error(
                    f"Groom already exists: {groom_name}",
                    "Set replace_existing=true only when replacing a generated groom with the same name.",
                )
            _remove_existing_groom(bpy, groom_name)
            if bpy.data.objects.get(groom_name) is not None:
                return skill_error(
                    f"Could not replace groom: {groom_name}", "The existing object is not a generated groom."
                )

        bias = _normalize(_vector(direction_bias) or _UP)
        rng = random.Random(int(seed))
        indices = list(range(len(root_vertices)))
        rng.shuffle(indices)
        curve_data = bpy.data.curves.new(name=groom_name, type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.resolution_u = 2
        curve_data.bevel_depth = width_value
        curve_data.bevel_resolution = 1
        collection = _ensure_collection(bpy, collection_name)
        groom = bpy.data.objects.new(groom_name, curve_data)
        collection.objects.link(groom)

        for guide_index in range(int(guide_count)):
            vertex = root_vertices[indices[guide_index % len(indices)]]
            root = _transform_point(scalp, getattr(vertex, "co", _UP))
            normal = _transform_normal(scalp, getattr(vertex, "normal", _UP))
            direction = _normalize(_add(_scale(normal, normal_weight_value), _scale(bias, 1.0 - normal_weight_value)))
            side = _normalize(_cross(direction, _UP), fallback=(1.0, 0.0, 0.0))
            other_side = _normalize(_cross(direction, side), fallback=(0.0, 1.0, 0.0))
            phase = rng.uniform(0.0, math.tau)
            amplitude = length_value * curl_value * rng.uniform(0.35, 1.0) * 0.25
            # NURBS keeps the guide tangent continuous between samples.  The
            # old POLY splines exposed every generated segment as a visible
            # corner when the guide count was increased on a dense hair shell.
            spline = curve_data.splines.new("NURBS")
            spline.order_u = min(3, int(segments))
            spline.use_endpoint_u = True
            spline.use_cyclic_u = False
            spline.resolution_u = 4
            spline.points.add(int(segments) - 1)
            for point_index, point in enumerate(spline.points):
                t = point_index / float(int(segments) - 1)
                forward = _scale(direction, length_value * t)
                wave = math.sin(math.pi * t + phase) * amplitude * t
                lateral = _add(
                    _scale(side, wave),
                    _scale(other_side, math.cos(math.pi * t + phase) * amplitude * 0.35 * t),
                )
                point.co = (*_add(root, _add(forward, lateral)), 1.0)

        material = _ensure_material(bpy, material_name, hair_color, roughness_value)
        curve_data.materials.append(material)
        parameters = {
            "guide_count": int(guide_count),
            "segments": int(segments),
            "length": length_value,
            "width": width_value,
            "normal_weight": normal_weight_value,
            "direction_bias": list(bias),
            "curl": curl_value,
            "seed": int(seed),
            "root_height_min": root_height_min_value,
            "root_height_max": root_height_max_value,
        }
        _custom_set(groom, _GROOM_MARKER, _GROOM_VERSION)
        _custom_set(groom, _GROOM_SOURCE_KEY, scalp_object_name)
        _custom_set(groom, _GROOM_PARAMETERS_KEY, json.dumps(parameters, sort_keys=True))
        _custom_set(
            groom,
            _GROOM_STYLE_KEY,
            json.dumps({"width": width_value, "roughness": roughness_value}, sort_keys=True),
        )
        return skill_success(
            f"Created groom guides: {groom_name}",
            object_name=groom_name,
            source_object=scalp_object_name,
            guide_count=int(guide_count),
            point_count=_point_count(groom),
            collection_name=getattr(collection, "name", collection_name),
            material_name=getattr(material, "name", material_name),
            parameters=parameters,
            prompt="Use inspect_grooms to verify the generated guides, then set_groom_style to tune width, color, or length.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create groom guides on {scalp_object_name}")


def inspect_grooms(object_name: str | None = None) -> dict:
    """Inspect one generated groom or list all generated grooms."""
    try:
        import bpy

        if object_name:
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return skill_error(f"Object not found: {object_name}", "Pass a generated groom object name.")
            if _custom_get(obj, _GROOM_MARKER) != _GROOM_VERSION:
                return skill_error(
                    f"Object is not a generated groom: {object_name}",
                    "Inspect only objects created by blender-groom.",
                )
            return skill_success("Groom inspected", groom=_summary(obj))
        grooms = [_summary(obj) for obj in bpy.data.objects if _custom_get(obj, _GROOM_MARKER) == _GROOM_VERSION]
        return skill_success("Grooms inspected", grooms=grooms, count=len(grooms))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect grooms")


def set_groom_style(
    object_name: str,
    width: float | None = None,
    length_scale: float | None = None,
    hair_color: Sequence[float] | None = None,
    roughness: float | None = None,
    material_name: str | None = None,
) -> dict:
    """Tune a generated groom while preserving each guide root position."""
    if width is None and length_scale is None and hair_color is None and roughness is None and material_name is None:
        return skill_error(
            "No style changes",
            "Pass at least one of width, length_scale, hair_color, roughness, or material_name.",
        )
    try:
        width_value = float(width) if width is not None else None
        length_scale_value = float(length_scale) if length_scale is not None else None
        roughness_value = float(roughness) if roughness is not None else None
    except (TypeError, ValueError):
        return skill_error("Invalid style parameters", "width, length_scale, and roughness must be numeric.")
    if width_value is not None and (not math.isfinite(width_value) or not 0.000001 < width_value <= 1.0):
        return skill_error("Invalid width", "width must be greater than 0 and no more than 1 Blender unit.")
    if length_scale_value is not None and (
        not math.isfinite(length_scale_value) or not 0.0 < length_scale_value <= 10.0
    ):
        return skill_error("Invalid length_scale", "length_scale must be greater than 0 and no more than 10.")
    if roughness_value is not None and (not math.isfinite(roughness_value) or not 0.0 <= roughness_value <= 1.0):
        return skill_error("Invalid roughness", "roughness must be between 0 and 1.")
    color_values = None
    if hair_color is not None:
        if isinstance(hair_color, (str, bytes)) or len(hair_color) not in (3, 4):
            return skill_error("Invalid hair_color", "hair_color must contain three or four values.")
        try:
            color_values = [float(value) for value in hair_color]
        except (TypeError, ValueError):
            return skill_error("Invalid hair_color", "hair_color must contain numeric values.")
        if not all(0.0 <= value <= 1.0 for value in color_values):
            return skill_error("Invalid hair_color", "hair_color values must be between 0 and 1.")

    try:
        import bpy

        groom = bpy.data.objects.get(object_name)
        if groom is None:
            return skill_error(f"Object not found: {object_name}", "Pass a generated groom object name.")
        if _custom_get(groom, _GROOM_MARKER) != _GROOM_VERSION or getattr(groom, "type", None) != "CURVE":
            return skill_error(
                f"Object is not a generated groom: {object_name}",
                "Style edits are restricted to blender-groom output.",
            )
        curve_data = groom.data
        if width_value is not None:
            curve_data.bevel_depth = width_value
        if length_scale_value is not None:
            for spline in curve_data.splines:
                points = list(spline.points)
                if not points:
                    continue
                root = tuple(float(points[0].co[index]) for index in range(3))
                for point in points[1:]:
                    current = tuple(float(point.co[index]) for index in range(3))
                    scaled = _add(root, _scale(_sub(current, root), length_scale_value))
                    point.co = (*scaled, 1.0)
        materials = list(getattr(curve_data, "materials", []))
        existing_material = materials[0] if materials else None
        selected_material_name = material_name or getattr(existing_material, "name", _DEFAULT_MATERIAL_NAME)
        if (
            material_name is not None
            or hair_color is not None
            or roughness_value is not None
            or existing_material is None
        ):
            material = _ensure_material(bpy, selected_material_name, color_values, roughness_value)
            if materials:
                curve_data.materials[0] = material
            else:
                curve_data.materials.append(material)
        style = {
            "width": float(getattr(curve_data, "bevel_depth", width_value or 0.0)),
            "length_scale": length_scale_value if length_scale_value is not None else 1.0,
            "material_name": selected_material_name,
            "roughness": roughness_value,
        }
        if color_values is not None:
            style["hair_color"] = color_values
        _custom_set(groom, _GROOM_STYLE_KEY, json.dumps(style, sort_keys=True))
        return skill_success(
            f"Updated groom style: {object_name}",
            object_name=object_name,
            guide_count=len(list(curve_data.splines)),
            point_count=_point_count(groom),
            style=style,
            prompt="Use inspect_grooms to read back the applied style and guide counts.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update groom style: {object_name}")


def shape_groom_guides(
    object_name: str,
    length_scale: float | None = None,
    direction_bias: Sequence[float] | None = None,
    direction_strength: float | None = None,
    curl: float | None = None,
    taper: float | None = None,
    seed: int = 0,
) -> dict:
    """Comb and shape generated guides while preserving every root point."""
    if all(value is None for value in (length_scale, direction_bias, curl, taper)):
        return skill_error(
            "No guide shape changes",
            "Pass at least one of length_scale, direction_bias, curl, or taper.",
        )
    if direction_strength is not None and direction_bias is None:
        return skill_error("Invalid direction_strength", "direction_strength requires direction_bias.")
    try:
        length_scale_value = float(length_scale) if length_scale is not None else 1.0
        direction_strength_value = float(direction_strength) if direction_strength is not None else 1.0
        curl_value = float(curl) if curl is not None else None
        taper_value = float(taper) if taper is not None else None
    except (TypeError, ValueError):
        return skill_error(
            "Invalid guide shape parameters",
            "length_scale, direction_strength, curl, and taper must be numeric.",
        )
    if not math.isfinite(length_scale_value) or not 0.0 < length_scale_value <= 10.0:
        return skill_error("Invalid length_scale", "length_scale must be greater than 0 and no more than 10.")
    if not math.isfinite(direction_strength_value) or not 0.0 <= direction_strength_value <= 1.0:
        return skill_error("Invalid direction_strength", "direction_strength must be between 0 and 1.")
    if curl_value is not None and (not math.isfinite(curl_value) or not 0.0 <= curl_value <= 1.0):
        return skill_error("Invalid curl", "curl must be between 0 and 1.")
    if taper_value is not None and (not math.isfinite(taper_value) or not 0.0 <= taper_value <= 1.0):
        return skill_error("Invalid taper", "taper must be between 0 and 1.")
    bias = _vector(direction_bias) if direction_bias is not None else None
    if direction_bias is not None and bias is None:
        return skill_error("Invalid direction_bias", "direction_bias must contain three finite numbers.")
    try:
        if isinstance(seed, bool):
            raise ValueError
        seed_value = int(seed)
    except (TypeError, ValueError):
        return skill_error("Invalid seed", "seed must be an integer.")

    try:
        import bpy

        groom, error = _generated_groom(bpy, object_name)
        if error:
            return error
        curve_data = groom.data
        rng = random.Random(seed_value)
        changed_points = 0
        for spline in getattr(curve_data, "splines", []):
            points = list(getattr(spline, "points", []))
            if len(points) < 2:
                continue
            root = tuple(float(points[0].co[index]) for index in range(3))
            endpoint = tuple(float(points[-1].co[index]) for index in range(3))
            endpoint_vector = _sub(endpoint, root)
            current_direction = _normalize(endpoint_vector)
            if bias is not None:
                current_direction = _normalize(
                    _add(
                        _scale(current_direction, 1.0 - direction_strength_value),
                        _scale(bias, direction_strength_value),
                    )
                )
            if bias is not None or length_scale is not None:
                for point in points[1:]:
                    current = tuple(float(point.co[index]) for index in range(3))
                    current_length = math.sqrt(_dot(_sub(current, root), _sub(current, root)))
                    shaped = _add(root, _scale(current_direction, current_length * length_scale_value))
                    point.co = (*shaped, 1.0)
                    changed_points += 1
            if curl_value is not None:
                side = _normalize(_cross(current_direction, _UP), fallback=(1.0, 0.0, 0.0))
                other_side = _normalize(_cross(current_direction, side), fallback=(0.0, 1.0, 0.0))
                phase = rng.uniform(0.0, math.tau)
                guide_length = math.sqrt(_dot(endpoint_vector, endpoint_vector)) * length_scale_value
                amplitude = guide_length * curl_value * 0.25
                for point_index, point in enumerate(points[1:], start=1):
                    t = point_index / float(len(points) - 1)
                    wave = math.sin(math.pi * t + phase) * amplitude * t
                    current = tuple(float(point.co[index]) for index in range(3))
                    lateral = _add(
                        _scale(side, wave),
                        _scale(other_side, math.cos(math.pi * t + phase) * amplitude * 0.35 * t),
                    )
                    point.co = (*_add(current, lateral), 1.0)
                    changed_points += 1
            if taper_value is not None:
                for point_index, point in enumerate(points):
                    if hasattr(point, "radius"):
                        t = point_index / float(len(points) - 1)
                        point.radius = max(0.01, 1.0 - taper_value * t)

        shape = _json_value(_custom_get(groom, _GROOM_SHAPE_KEY, {}), {})
        if not isinstance(shape, dict):
            shape = {}
        if length_scale is not None:
            shape["length_scale"] = length_scale_value
        if bias is not None:
            shape["direction_bias"] = list(_normalize(bias))
            shape["direction_strength"] = direction_strength_value
        if curl_value is not None:
            shape["curl"] = curl_value
            shape["seed"] = seed_value
        if taper_value is not None:
            shape["taper"] = taper_value
        _custom_set(groom, _GROOM_SHAPE_KEY, json.dumps(shape, sort_keys=True))
        return skill_success(
            f"Shaped groom guides: {object_name}",
            object_name=object_name,
            guide_count=len(list(getattr(curve_data, "splines", []))),
            point_count=_point_count(groom),
            changed_point_count=changed_points,
            shape=shape,
            prompt="Use inspect_grooms to read back guide shape metadata before saving or exporting.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to shape groom guides: {object_name}")


def thin_groom_guides(object_name: str, density: float, seed: int = 0) -> dict:
    """Reduce guide count deterministically while keeping a representative sample."""
    try:
        density_value = float(density)
    except (TypeError, ValueError):
        return skill_error("Invalid density", "density must be numeric.")
    if not math.isfinite(density_value) or not 0.0 < density_value <= 1.0:
        return skill_error("Invalid density", "density must be greater than 0 and no more than 1.")
    try:
        if isinstance(seed, bool):
            raise ValueError
        seed_value = int(seed)
    except (TypeError, ValueError):
        return skill_error("Invalid seed", "seed must be an integer.")

    try:
        import bpy

        groom, error = _generated_groom(bpy, object_name)
        if error:
            return error
        splines = list(getattr(groom.data, "splines", []))
        current_count = len(splines)
        target_count = max(1, int(round(current_count * density_value))) if current_count else 0
        if target_count < current_count:
            rng = random.Random(seed_value)
            keep_indices = set(rng.sample(range(current_count), target_count))
            for index, spline in enumerate(splines):
                if index not in keep_indices:
                    groom.data.splines.remove(spline)
        actual_count = len(list(getattr(groom.data, "splines", [])))
        parameters = _json_value(_custom_get(groom, _GROOM_PARAMETERS_KEY, {}), {})
        if not isinstance(parameters, dict):
            parameters = {}
        parameters["guide_count"] = actual_count
        parameters["density"] = density_value
        parameters["density_seed"] = seed_value
        _custom_set(groom, _GROOM_PARAMETERS_KEY, json.dumps(parameters, sort_keys=True))
        return skill_success(
            f"Thinned groom guides: {object_name}",
            object_name=object_name,
            density=density_value,
            seed=seed_value,
            guide_count=actual_count,
            removed_guide_count=current_count - actual_count,
            point_count=_point_count(groom),
            prompt="Use inspect_grooms to verify the reduced guide count and then tune style if needed.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to thin groom guides: {object_name}")


def duplicate_groom(
    object_name: str,
    new_object_name: str,
    collection_name: str | None = None,
    replace_existing: bool = False,
) -> dict:
    """Create a generated groom variant with independent curve data."""
    if not new_object_name or not new_object_name.strip():
        return skill_error("Invalid new_object_name", "new_object_name must be a non-empty string.")
    if new_object_name == object_name:
        return skill_error("Invalid new_object_name", "new_object_name must differ from object_name.")
    try:
        import bpy

        source, error = _generated_groom(bpy, object_name)
        if error:
            return error
        existing = bpy.data.objects.get(new_object_name)
        if existing is not None:
            if not replace_existing:
                return skill_error(
                    f"Object already exists: {new_object_name}",
                    "Set replace_existing=true only when replacing a generated groom variant.",
                )
            if _custom_get(existing, _GROOM_MARKER) != _GROOM_VERSION:
                return skill_error(
                    f"Could not replace object: {new_object_name}",
                    "The existing object is not a generated groom.",
                )
            _remove_existing_groom(bpy, new_object_name)
        curve_data = _copy_curve_data(bpy, source.data, new_object_name)
        collection = _ensure_collection(bpy, collection_name)
        duplicate = bpy.data.objects.new(new_object_name, curve_data)
        collection.objects.link(duplicate)
        for key in (_GROOM_MARKER, _GROOM_SOURCE_KEY, _GROOM_PARAMETERS_KEY, _GROOM_STYLE_KEY, _GROOM_SHAPE_KEY):
            value = _custom_get(source, key, None)
            if value is not None:
                _custom_set(duplicate, key, value)
        return skill_success(
            f"Duplicated groom: {new_object_name}",
            object_name=new_object_name,
            source_groom=object_name,
            guide_count=len(list(getattr(curve_data, "splines", []))),
            point_count=_point_count(duplicate),
            collection_name=getattr(collection, "name", collection_name),
            prompt="Use set_groom_style or shape_groom_guides to create a groom variant.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to duplicate groom: {object_name}")


def delete_groom(object_name: str, remove_unused_materials: bool = False) -> dict:
    """Delete one generated groom and release its curve data."""
    try:
        import bpy

        groom, error = _generated_groom(bpy, object_name)
        if error:
            return error
        materials = list(getattr(groom.data, "materials", []))
        data = getattr(groom, "data", None)
        bpy.data.objects.remove(groom, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0:
            remover = getattr(bpy.data.curves, "remove", None)
            if callable(remover):
                remover(data)
        removed_materials = []
        if remove_unused_materials:
            material_store = getattr(bpy.data, "materials", None)
            remover = getattr(material_store, "remove", None)
            for material in materials:
                if getattr(material, "users", 1) == 0 and callable(remover):
                    remover(material)
                    removed_materials.append(getattr(material, "name", None))
        return skill_success(
            f"Deleted groom: {object_name}",
            object_name=object_name,
            removed_materials=removed_materials,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to delete groom: {object_name}")


def validate_groom_attachment(object_name: str, tolerance: float = 0.001, sample_limit: int = 128) -> dict:
    """Check that guide roots still have a nearby vertex on the source mesh."""
    try:
        tolerance_value = float(tolerance)
    except (TypeError, ValueError):
        return skill_error("Invalid tolerance", "tolerance must be numeric.")
    if not math.isfinite(tolerance_value) or not 0.0 < tolerance_value <= 10.0:
        return skill_error("Invalid tolerance", "tolerance must be greater than 0 and no more than 10.")
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int) or not 1 <= sample_limit <= 4096:
        return skill_error("Invalid sample_limit", "sample_limit must be an integer between 1 and 4096.")

    try:
        import bpy

        groom, error = _generated_groom(bpy, object_name)
        if error:
            return error
        source_name = _custom_get(groom, _GROOM_SOURCE_KEY)
        source = bpy.data.objects.get(source_name) if source_name else None
        if source is None or getattr(source, "type", None) != "MESH":
            return skill_success(
                f"Groom attachment checked: {object_name}",
                object_name=object_name,
                valid=False,
                source_object=source_name,
                reason="source_mesh_missing",
                sample_count=0,
                detached_root_count=0,
            )
        vertices = list(getattr(getattr(source, "data", None), "vertices", []))
        if not vertices:
            return skill_success(
                f"Groom attachment checked: {object_name}",
                object_name=object_name,
                valid=False,
                source_object=source_name,
                reason="source_mesh_empty",
                sample_count=0,
                detached_root_count=0,
            )
        splines = list(getattr(getattr(groom, "data", None), "splines", []))
        sampled_splines = splines[:sample_limit]
        if len(splines) > sample_limit:
            stride = max(1, len(splines) // sample_limit)
            sampled_splines = [splines[index] for index in range(0, len(splines), stride)][:sample_limit]
        vertex_positions = [
            _transform_point(source, getattr(vertex, "co", _UP))
            for vertex in vertices
            if _vector(getattr(vertex, "co", None)) is not None
        ]
        if not vertex_positions:
            return skill_success(
                f"Groom attachment checked: {object_name}",
                object_name=object_name,
                valid=False,
                source_object=source_name,
                reason="source_mesh_has_no_valid_vertices",
                sample_count=0,
                detached_root_count=0,
            )
        detached_count = 0
        max_distance = 0.0
        for spline in sampled_splines:
            points = list(getattr(spline, "points", []))
            if not points:
                continue
            root = tuple(float(points[0].co[index]) for index in range(3))
            nearest_distance = min(
                math.sqrt(_dot(_sub(root, vertex_position), _sub(root, vertex_position)))
                for vertex_position in vertex_positions
            )
            max_distance = max(max_distance, nearest_distance)
            if nearest_distance > tolerance_value:
                detached_count += 1
        sample_count = len(sampled_splines)
        return skill_success(
            f"Groom attachment checked: {object_name}",
            object_name=object_name,
            source_object=source_name,
            valid=detached_count == 0,
            sample_count=sample_count,
            detached_root_count=detached_count,
            tolerance=tolerance_value,
            max_root_distance=max_distance,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to validate groom attachment: {object_name}")
