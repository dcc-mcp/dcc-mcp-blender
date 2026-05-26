"""Shared implementations for bundled Blender UV skill tools."""

from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any, Iterable, Mapping

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_AXES = {
    "x": (1, 2),
    "y": (0, 2),
    "z": (0, 1),
}
_PROJECT_METHODS = {"planar", "cube", "bounds", "smart", "sphere", "cylinder", "view"}
_UNWRAP_METHODS = {"angle_based", "conformal", "smart"}


def _require_mesh_object(bpy: Any, object_name: str) -> tuple[Any | None, dict | None]:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    if getattr(obj, "type", None) != "MESH":
        return None, skill_error(f"{object_name} is not a mesh", f"Object type is {getattr(obj, 'type', None)}.")
    return obj, None


def _validate_name(value: str, label: str) -> dict | None:
    if not isinstance(value, str) or not value.strip():
        return skill_error(f"Invalid {label}", f"{label} must be a non-empty string.")
    return None


def _validate_margin(margin: float) -> dict | None:
    if not isinstance(margin, (int, float)) or not isfinite(float(margin)):
        return skill_error("Invalid margin", "margin must be a finite number.")
    if float(margin) < 0 or float(margin) >= 0.5:
        return skill_error("Invalid margin", "margin must be in the range [0.0, 0.5).")
    return None


def _uv_layers(mesh: Any) -> Any:
    return mesh.uv_layers


def _get_uv_layer(mesh: Any, name: str | None = None) -> Any | None:
    layers = _uv_layers(mesh)
    if name:
        getter = getattr(layers, "get", None)
        if callable(getter):
            return getter(name)
        for layer in layers:
            if getattr(layer, "name", None) == name:
                return layer
        return None
    active = getattr(layers, "active", None)
    if active is not None:
        return active
    return next(iter(layers), None)


def _ensure_uv_layer(mesh: Any, name: str | None = None, *, set_active: bool = True) -> Any:
    existing = _get_uv_layer(mesh, name)
    if existing is not None:
        if set_active:
            _set_active_uv_layer(mesh, existing)
        return existing

    layer_name = name or "UVMap"
    layer = mesh.uv_layers.new(name=layer_name)
    if set_active:
        _set_active_uv_layer(mesh, layer)
    return layer


def _set_active_uv_layer(mesh: Any, layer: Any) -> None:
    layers = _uv_layers(mesh)
    try:
        layers.active = layer
    except Exception:
        pass
    for index, existing in enumerate(layers):
        if existing is layer or getattr(existing, "name", None) == getattr(layer, "name", None):
            try:
                layers.active_index = index
            except Exception:
                pass
            break


def _layer_summary(mesh: Any, layer: Any, index: int) -> dict:
    active = _get_uv_layer(mesh)
    return {
        "name": getattr(layer, "name", ""),
        "index": index,
        "active": layer is active or getattr(layer, "name", None) == getattr(active, "name", None),
        "coordinate_count": len(getattr(layer, "data", [])),
    }


def _mesh_uv_context(obj: Any) -> dict:
    mesh = obj.data
    layers = list(_uv_layers(mesh))
    active = _get_uv_layer(mesh)
    return {
        "object_name": obj.name,
        "mesh_name": mesh.name,
        "uv_map_count": len(layers),
        "active_uv_map": getattr(active, "name", None),
        "uv_maps": [_layer_summary(mesh, layer, index) for index, layer in enumerate(layers)],
    }


def _co(value: Any) -> tuple[float, float, float]:
    return (float(value[0]), float(value[1]), float(value[2]))


def _uv_pair(value: Any) -> list[float]:
    return [float(value[0]), float(value[1])]


def _uv_key(value: Any) -> tuple[float, float]:
    u, v = _uv_pair(value)
    return (round(u, 6), round(v, 6))


def _set_uv(loop_data: Any, u: float, v: float) -> None:
    try:
        loop_data.uv = (float(u), float(v))
    except Exception:
        loop_data.uv[0] = float(u)
        loop_data.uv[1] = float(v)


def _normalize_pairs(pairs: Mapping[int, tuple[float, float]], margin: float) -> dict[int, tuple[float, float]]:
    if not pairs:
        return {}
    us = [pair[0] for pair in pairs.values()]
    vs = [pair[1] for pair in pairs.values()]
    min_u, max_u = min(us), max(us)
    min_v, max_v = min(vs), max(vs)
    span_u = max(max_u - min_u, 1e-9)
    span_v = max(max_v - min_v, 1e-9)
    scale = max(0.0, 1.0 - (margin * 2.0))
    return {
        loop_index: (
            margin + ((u - min_u) / span_u) * scale,
            margin + ((v - min_v) / span_v) * scale,
        )
        for loop_index, (u, v) in pairs.items()
    }


def _update_mesh(mesh: Any) -> None:
    update = getattr(mesh, "update", None)
    if callable(update):
        update()


def list_uv_maps(object_name: str) -> dict:
    """List UV maps on a mesh object."""
    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        return skill_success(
            f"UV maps for {object_name}",
            **_mesh_uv_context(obj),
            prompt="Use create_uv_map, copy_uv_map, or get_uv_info for detailed UV work.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to list UV maps for {object_name}")


def create_uv_map(object_name: str, name: str, set_active: bool = True) -> dict:
    """Create a UV map on a mesh object."""
    name_error = _validate_name(name, "name")
    if name_error:
        return name_error
    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        mesh = obj.data
        if _get_uv_layer(mesh, name) is not None:
            return skill_error(f"UV map already exists: {name}", f"{object_name} already has a UV map named '{name}'.")

        layer = mesh.uv_layers.new(name=name)
        if set_active:
            _set_active_uv_layer(mesh, layer)
        _update_mesh(mesh)
        return skill_success(
            f"Created UV map {name} on {object_name}",
            created_uv_map=layer.name,
            set_active=set_active,
            **_mesh_uv_context(obj),
            prompt="Use project_uvs or unwrap_uvs to populate the new UV map.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create UV map {name} on {object_name}")


def delete_uv_map(object_name: str, name: str) -> dict:
    """Delete a UV map from a mesh object."""
    name_error = _validate_name(name, "name")
    if name_error:
        return name_error
    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        mesh = obj.data
        layer = _get_uv_layer(mesh, name)
        if layer is None:
            return skill_error(f"UV map not found: {name}", f"{object_name} has no UV map named '{name}'.")

        mesh.uv_layers.remove(layer)
        _update_mesh(mesh)
        return skill_success(
            f"Deleted UV map {name} from {object_name}",
            deleted_uv_map=name,
            **_mesh_uv_context(obj),
            prompt="Use list_uv_maps to confirm the remaining active UV map.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to delete UV map {name} from {object_name}")


def copy_uv_map(object_name: str, source: str, target: str) -> dict:
    """Copy UV coordinates from one UV map to a new UV map."""
    for value, label in ((source, "source"), (target, "target")):
        name_error = _validate_name(value, label)
        if name_error:
            return name_error
    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        mesh = obj.data
        source_layer = _get_uv_layer(mesh, source)
        if source_layer is None:
            return skill_error(f"Source UV map not found: {source}", f"{object_name} has no UV map named '{source}'.")
        if _get_uv_layer(mesh, target) is not None:
            return skill_error(f"Target UV map already exists: {target}", "Choose a new target UV map name.")

        target_layer = mesh.uv_layers.new(name=target)
        for src_loop, dst_loop in zip(source_layer.data, target_layer.data):
            src_u, src_v = _uv_pair(src_loop.uv)
            _set_uv(dst_loop, src_u, src_v)
        _set_active_uv_layer(mesh, target_layer)
        _update_mesh(mesh)
        return skill_success(
            f"Copied UV map {source} to {target} on {object_name}",
            source_uv_map=source,
            target_uv_map=target,
            copied_coordinate_count=len(target_layer.data),
            **_mesh_uv_context(obj),
            prompt="Use normalize_uvs or pack_uvs to prepare the copied UV map for texturing.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to copy UV map {source} to {target} on {object_name}")


def get_uv_info(object_name: str) -> dict:
    """Return UV map and coordinate statistics for a mesh object."""
    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        mesh = obj.data
        active = _get_uv_layer(mesh)
        polygons = list(getattr(mesh, "polygons", []))
        loop_count = sum(len(getattr(poly, "loop_indices", [])) for poly in polygons)
        island_count = len(_calculate_uv_islands(mesh, active)) if active is not None else 0
        return skill_success(
            f"UV info for {object_name}",
            polygon_count=len(polygons),
            loop_count=loop_count,
            uv_coordinate_count=len(getattr(active, "data", [])) if active is not None else 0,
            island_count=island_count,
            has_uvs=active is not None,
            **_mesh_uv_context(obj),
            prompt="Use get_uv_islands for shell bounds or project_uvs/unwrap_uvs for UV generation.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to get UV info for {object_name}")


def get_uv_islands(object_name: str, uv_map: str | None = None) -> dict:
    """Return UV island summaries for a mesh UV map."""
    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        mesh = obj.data
        layer = _get_uv_layer(mesh, uv_map)
        if layer is None:
            label = uv_map or "active UV map"
            return skill_error(f"UV map not found: {label}", f"{object_name} has no {label}.")

        islands = _calculate_uv_islands(mesh, layer)
        return skill_success(
            f"Found {len(islands)} UV island(s) on {object_name}",
            object_name=obj.name,
            mesh_name=mesh.name,
            uv_map=layer.name,
            island_count=len(islands),
            islands=islands,
            prompt="Use pack_uvs to arrange islands or normalize_uvs to fit coordinates into 0-1 space.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to get UV islands for {object_name}")


def _calculate_uv_islands(mesh: Any, layer: Any) -> list[dict]:
    polygons = list(getattr(mesh, "polygons", []))
    if not polygons:
        return []

    parent = list(range(len(polygons)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    edge_owner: dict[tuple, int] = {}
    loops = getattr(mesh, "loops", [])
    for poly_index, poly in enumerate(polygons):
        loop_indices = list(getattr(poly, "loop_indices", []))
        for left, right in zip(loop_indices, loop_indices[1:] + loop_indices[:1]):
            left_loop = loops[left]
            right_loop = loops[right]
            key_parts = [
                (getattr(left_loop, "vertex_index", left), _uv_key(layer.data[left].uv)),
                (getattr(right_loop, "vertex_index", right), _uv_key(layer.data[right].uv)),
            ]
            key = tuple(sorted(key_parts))
            owner = edge_owner.get(key)
            if owner is None:
                edge_owner[key] = poly_index
            else:
                union(poly_index, owner)

    groups: dict[int, list[Any]] = defaultdict(list)
    for poly_index, poly in enumerate(polygons):
        groups[find(poly_index)].append(poly)

    islands = []
    for island_index, faces in enumerate(groups.values()):
        loop_indices = sorted({loop_index for face in faces for loop_index in getattr(face, "loop_indices", [])})
        coords = [_uv_pair(layer.data[loop_index].uv) for loop_index in loop_indices]
        min_u = min((coord[0] for coord in coords), default=0.0)
        max_u = max((coord[0] for coord in coords), default=0.0)
        min_v = min((coord[1] for coord in coords), default=0.0)
        max_v = max((coord[1] for coord in coords), default=0.0)
        islands.append(
            {
                "index": island_index,
                "face_indices": [int(getattr(face, "index", fallback)) for fallback, face in enumerate(faces)],
                "face_count": len(faces),
                "loop_count": len(loop_indices),
                "bounds": {
                    "min": [min_u, min_v],
                    "max": [max_u, max_v],
                    "size": [max_u - min_u, max_v - min_v],
                },
            }
        )
    return islands


def project_uvs(object_name: str, method: str = "planar", axis: str = "z", margin: float = 0.0) -> dict:
    """Project UV coordinates onto a mesh."""
    margin_error = _validate_margin(margin)
    if margin_error:
        return margin_error
    method_key = method.lower().replace("-", "_")
    axis_key = axis.lower()
    if method_key not in _PROJECT_METHODS:
        return skill_error("Invalid projection method", f"Use one of: {', '.join(sorted(_PROJECT_METHODS))}.")
    if axis_key not in _AXES:
        return skill_error("Invalid axis", "axis must be one of: x, y, z.")

    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        mesh = obj.data
        layer = _ensure_uv_layer(mesh, set_active=True)

        if method_key in {"smart", "sphere", "cylinder", "view"}:
            operator_result = _run_projection_operator(bpy, obj, method_key, float(margin))
            _update_mesh(mesh)
            return skill_success(
                f"Projected UVs on {object_name} using {method_key}",
                uv_map=layer.name,
                method=method_key,
                axis=axis_key,
                margin=float(margin),
                operator_result=operator_result,
                **_mesh_uv_context(obj),
                prompt="Use get_uv_islands or pack_uvs to inspect and arrange the generated UV shells.",
            )

        assignments = _project_mesh_coordinates(mesh, layer, method_key, axis_key, float(margin))
        _update_mesh(mesh)
        return skill_success(
            f"Projected UVs on {object_name} using {method_key}",
            uv_map=layer.name,
            method=method_key,
            axis=axis_key,
            margin=float(margin),
            uv_coordinate_count=len(assignments),
            **_mesh_uv_context(obj),
            prompt="Use get_uv_islands or pack_uvs to inspect and arrange the generated UV shells.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to project UVs on {object_name}")


def _project_mesh_coordinates(
    mesh: Any, layer: Any, method: str, axis: str, margin: float
) -> dict[int, tuple[float, float]]:
    loops = getattr(mesh, "loops", [])
    vertices = getattr(mesh, "vertices", [])
    polygons = list(getattr(mesh, "polygons", []))
    raw: dict[int, tuple[float, float]] = {}

    if method in {"planar", "bounds"}:
        axes = _AXES[axis]
        for poly in polygons:
            for loop_index in getattr(poly, "loop_indices", []):
                vertex_index = getattr(loops[loop_index], "vertex_index", loop_index)
                co = _co(vertices[vertex_index].co)
                raw[loop_index] = (co[axes[0]], co[axes[1]])
    elif method == "cube":
        for poly in polygons:
            normal = _co(getattr(poly, "normal", (0.0, 0.0, 1.0)))
            drop_axis = max(range(3), key=lambda index: abs(normal[index]))
            axes = tuple(index for index in range(3) if index != drop_axis)
            for loop_index in getattr(poly, "loop_indices", []):
                vertex_index = getattr(loops[loop_index], "vertex_index", loop_index)
                co = _co(vertices[vertex_index].co)
                raw[loop_index] = (co[axes[0]], co[axes[1]])

    assignments = _normalize_pairs(raw, margin)
    for loop_index, (u, v) in assignments.items():
        _set_uv(layer.data[loop_index], u, v)
    return assignments


def unwrap_uvs(object_name: str, method: str = "angle_based", margin: float = 0.001) -> dict:
    """Unwrap a mesh through Blender's UV operators."""
    margin_error = _validate_margin(margin)
    if margin_error:
        return margin_error
    method_key = method.lower().replace("-", "_")
    if method_key not in _UNWRAP_METHODS:
        return skill_error("Invalid unwrap method", f"Use one of: {', '.join(sorted(_UNWRAP_METHODS))}.")

    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        mesh = obj.data
        layer = _ensure_uv_layer(mesh, set_active=True)
        if method_key == "smart":
            operator_result = _run_uv_edit_operator(
                bpy,
                obj,
                "smart_project",
                island_margin=float(margin),
                correct_aspect=True,
            )
        else:
            operator_result = _run_uv_edit_operator(
                bpy,
                obj,
                "unwrap",
                method=method_key.upper(),
                margin=float(margin),
            )
        _update_mesh(mesh)
        return skill_success(
            f"Unwrapped UVs on {object_name} using {method_key}",
            uv_map=layer.name,
            method=method_key,
            margin=float(margin),
            operator_result=operator_result,
            **_mesh_uv_context(obj),
            prompt="Use get_uv_islands to inspect shell count or pack_uvs to arrange the unwrap.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to unwrap UVs on {object_name}")


def pack_uvs(
    object_name: str,
    margin: float = 0.001,
    rotate: bool = True,
    normalize: bool = True,
) -> dict:
    """Pack UV islands through Blender's UV operator."""
    margin_error = _validate_margin(margin)
    if margin_error:
        return margin_error
    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        mesh = obj.data
        layer = _get_uv_layer(mesh)
        if layer is None:
            return skill_error(f"No UV maps on {object_name}", "Create or unwrap a UV map before packing islands.")

        operator_result = _run_uv_edit_operator(
            bpy,
            obj,
            "pack_islands",
            margin=float(margin),
            rotate=bool(rotate),
        )
        if normalize:
            normalize_result = _normalize_layer(layer, float(margin))
        else:
            normalize_result = {"normalized_coordinate_count": 0}
        _update_mesh(mesh)
        return skill_success(
            f"Packed UVs on {object_name}",
            uv_map=layer.name,
            margin=float(margin),
            rotate=bool(rotate),
            normalize=bool(normalize),
            operator_result=operator_result,
            **normalize_result,
            **_mesh_uv_context(obj),
            prompt="Use get_uv_info or get_uv_islands to inspect the packed result.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to pack UVs on {object_name}")


def normalize_uvs(object_name: str, uv_map: str | None = None) -> dict:
    """Normalize UV coordinates into 0-1 space."""
    try:
        import bpy

        obj, error = _require_mesh_object(bpy, object_name)
        if error:
            return error
        mesh = obj.data
        layer = _get_uv_layer(mesh, uv_map)
        if layer is None:
            label = uv_map or "active UV map"
            return skill_error(f"UV map not found: {label}", f"{object_name} has no {label}.")

        normalized = _normalize_layer(layer, 0.0)
        _set_active_uv_layer(mesh, layer)
        _update_mesh(mesh)
        return skill_success(
            f"Normalized UVs on {object_name}",
            uv_map=layer.name,
            **normalized,
            **_mesh_uv_context(obj),
            prompt="Use pack_uvs if the UV islands still need layout spacing.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to normalize UVs on {object_name}")


def _normalize_layer(layer: Any, margin: float) -> dict:
    pairs = {index: tuple(_uv_pair(loop.uv)) for index, loop in enumerate(getattr(layer, "data", []))}
    assignments = _normalize_pairs(pairs, margin)
    for loop_index, (u, v) in assignments.items():
        _set_uv(layer.data[loop_index], u, v)
    return {
        "normalized_coordinate_count": len(assignments),
        "bounds": _bounds_for_uvs(layer.data),
    }


def _bounds_for_uvs(data: Iterable[Any]) -> dict:
    coords = [_uv_pair(loop.uv) for loop in data]
    min_u = min((coord[0] for coord in coords), default=0.0)
    max_u = max((coord[0] for coord in coords), default=0.0)
    min_v = min((coord[1] for coord in coords), default=0.0)
    max_v = max((coord[1] for coord in coords), default=0.0)
    return {
        "min": [min_u, min_v],
        "max": [max_u, max_v],
        "size": [max_u - min_u, max_v - min_v],
    }


def _run_projection_operator(bpy: Any, obj: Any, method: str, margin: float) -> list[str]:
    if method == "smart":
        return _run_uv_edit_operator(bpy, obj, "smart_project", island_margin=margin, correct_aspect=True)
    if method == "sphere":
        return _run_uv_edit_operator(bpy, obj, "sphere_project", correct_aspect=True, scale_to_bounds=True)
    if method == "cylinder":
        return _run_uv_edit_operator(bpy, obj, "cylinder_project", correct_aspect=True, scale_to_bounds=True)
    return _run_uv_edit_operator(bpy, obj, "project_from_view", correct_aspect=True, scale_to_bounds=True)


def _run_uv_edit_operator(bpy: Any, obj: Any, operator_name: str, **kwargs: Any) -> list[str]:
    _select_mesh_object(bpy, obj)
    previous_mode = getattr(obj, "mode", "OBJECT")
    try:
        bpy.ops.object.mode_set(mode="EDIT")
        select_mode = getattr(bpy.ops.mesh, "select_mode", None)
        if callable(select_mode):
            _call_operator(select_mode, type="FACE")
        bpy.ops.mesh.select_all(action="SELECT")
        operator = getattr(bpy.ops.uv, operator_name)
        result = _call_operator(operator, **kwargs)
        return sorted(str(item) for item in result) if isinstance(result, set) else [str(result)]
    finally:
        target_mode = previous_mode if previous_mode in {"OBJECT", "EDIT"} else "OBJECT"
        try:
            bpy.ops.object.mode_set(mode=target_mode)
        except Exception:
            bpy.ops.object.mode_set(mode="OBJECT")


def _select_mesh_object(bpy: Any, obj: Any) -> None:
    select_all = getattr(bpy.ops.object, "select_all", None)
    if callable(select_all):
        _call_operator(select_all, action="DESELECT")
    select_set = getattr(obj, "select_set", None)
    if callable(select_set):
        select_set(True)
    bpy.context.view_layer.objects.active = obj


def _call_operator(operator: Any, **kwargs: Any) -> Any:
    allowed = _operator_property_names(operator)
    if allowed:
        kwargs = {key: value for key, value in kwargs.items() if key in allowed}
    return operator(**kwargs)


def _operator_property_names(operator: Any) -> set[str]:
    try:
        properties = operator.get_rna_type().properties
    except Exception:
        return set()
    names = set()
    for prop in properties:
        identifier = getattr(prop, "identifier", None)
        if identifier and identifier != "rna_type":
            names.add(identifier)
    return names
