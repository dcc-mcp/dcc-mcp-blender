"""Shared implementations for Blender mesh editing operation tools."""

from __future__ import annotations

from typing import Any, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_SEPARATE_MODES = {"selected": "SELECTED", "material": "MATERIAL", "loose": "LOOSE"}
_MIRROR_AXES = {"x": 0, "y": 1, "z": 2}


def _mesh_object(bpy: Any, object_name: str) -> tuple[Any | None, dict | None]:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    if getattr(obj, "type", None) != "MESH":
        return None, skill_error(f"{object_name} is not a mesh", f"Object type is {getattr(obj, 'type', None)}.")
    return obj, None


def _mesh_counts(obj: Any) -> dict:
    mesh = obj.data
    return {
        "object_name": obj.name,
        "mesh_name": mesh.name,
        "vertex_count": len(getattr(mesh, "vertices", [])),
        "edge_count": len(getattr(mesh, "edges", [])),
        "face_count": len(getattr(mesh, "polygons", [])),
        "loop_count": len(getattr(mesh, "loops", [])),
        "material_count": len(getattr(mesh, "materials", [])),
        "uv_map_count": len(getattr(mesh, "uv_layers", [])),
    }


def _tri_count(obj: Any) -> int:
    total = 0
    for poly in getattr(obj.data, "polygons", []):
        vertices = len(getattr(poly, "vertices", []))
        total += max(vertices - 2, 0)
    return total


def _select_active(bpy: Any, obj: Any) -> None:
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass
    try:
        bpy.ops.object.select_all(action="DESELECT")
    except Exception:
        pass
    select_set = getattr(obj, "select_set", None)
    if callable(select_set):
        select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.context.active_object = obj
    except Exception:
        pass


def _edit_select_all(bpy: Any, obj: Any) -> None:
    _select_active(bpy, obj)
    bpy.ops.object.mode_set(mode="EDIT")
    select_mode = getattr(bpy.ops.mesh, "select_mode", None)
    if callable(select_mode):
        select_mode(type="FACE")
    bpy.ops.mesh.select_all(action="SELECT")


def _return_object_mode(bpy: Any) -> None:
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass


def _call_mesh_operator(primary: Any, fallback: Any | None = None, **kwargs: Any) -> Any:
    try:
        return primary(**kwargs)
    except TypeError:
        filtered = {key: value for key, value in kwargs.items() if key not in {"threshold", "distance"}}
        try:
            return primary(**filtered)
        except TypeError:
            if fallback is None:
                raise
            return fallback(**kwargs)


def get_poly_count(object_name: str) -> dict:
    """Return mesh polygon counts and derived triangle count."""
    try:
        import bpy

        obj, error = _mesh_object(bpy, object_name)
        if error:
            return error
        return skill_success(
            f"Mesh counts for {obj.name}",
            triangle_count=_tri_count(obj),
            **_mesh_counts(obj),
            prompt="Use cleanup_mesh or triangulate_mesh when the topology needs editing.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to get poly count for {object_name}")


def cleanup_mesh(
    object_name: str,
    remove_doubles: bool = True,
    fix_normals: bool = True,
    delete_loose: bool = True,
    merge_threshold: float = 0.0001,
) -> dict:
    """Run common cleanup operators on a mesh."""
    if merge_threshold < 0:
        return skill_error("Invalid merge_threshold", "merge_threshold must be non-negative.")
    try:
        import bpy

        obj, error = _mesh_object(bpy, object_name)
        if error:
            return error
        before = _mesh_counts(obj)
        _edit_select_all(bpy, obj)
        operations = []
        if remove_doubles:
            merge = getattr(bpy.ops.mesh, "merge_by_distance", None)
            remove = getattr(bpy.ops.mesh, "remove_doubles", None)
            if callable(merge):
                _call_mesh_operator(merge, distance=merge_threshold)
            elif callable(remove):
                _call_mesh_operator(remove, threshold=merge_threshold)
            operations.append("remove_doubles")
        if fix_normals:
            bpy.ops.mesh.normals_make_consistent(inside=False)
            operations.append("fix_normals")
        if delete_loose:
            delete_loose_op = getattr(bpy.ops.mesh, "delete_loose", None)
            if callable(delete_loose_op):
                delete_loose_op()
            operations.append("delete_loose")
        _return_object_mode(bpy)
        after = _mesh_counts(obj)
        return skill_success(
            f"Cleaned mesh {obj.name}",
            operations=operations,
            before=before,
            after=after,
            object_name=obj.name,
            prompt="Use get_poly_count to inspect the cleaned mesh.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        _safe_object_mode()
        return skill_exception(exc, message=f"Failed to clean mesh {object_name}")


def triangulate_mesh(object_name: str) -> dict:
    """Triangulate mesh faces."""
    try:
        import bpy

        obj, error = _mesh_object(bpy, object_name)
        if error:
            return error
        before = _mesh_counts(obj)
        _edit_select_all(bpy, obj)
        bpy.ops.mesh.quads_convert_to_tris()
        _return_object_mode(bpy)
        after = _mesh_counts(obj)
        return skill_success(
            f"Triangulated mesh {obj.name}",
            before=before,
            after=after,
            object_name=obj.name,
            prompt="Use get_poly_count to inspect the triangulated result.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        _safe_object_mode()
        return skill_exception(exc, message=f"Failed to triangulate mesh {object_name}")


def separate_mesh(object_name: str, mode: str = "loose") -> dict:
    """Separate a mesh by selected faces, material, or loose parts."""
    mode_key = mode.lower()
    if mode_key not in _SEPARATE_MODES:
        return skill_error("Invalid separate mode", f"Use one of: {', '.join(sorted(_SEPARATE_MODES))}.")
    try:
        import bpy

        obj, error = _mesh_object(bpy, object_name)
        if error:
            return error
        before_names = {obj.name for obj in bpy.data.objects}
        _edit_select_all(bpy, obj)
        bpy.ops.mesh.separate(type=_SEPARATE_MODES[mode_key])
        _return_object_mode(bpy)
        after_names = {obj.name for obj in bpy.data.objects}
        created = sorted(after_names - before_names)
        return skill_success(
            f"Separated mesh {object_name}",
            object_name=object_name,
            mode=mode_key,
            created_objects=created,
            created_count=len(created),
            prompt="Use list_objects or set_selection to inspect the separated objects.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        _safe_object_mode()
        return skill_exception(exc, message=f"Failed to separate mesh {object_name}")


def combine_meshes(object_names: Sequence[str], new_name: str | None = None) -> dict:
    """Join multiple mesh objects into one mesh."""
    if not object_names or isinstance(object_names, str):
        return skill_error("Invalid object_names", "object_names must be a non-empty list of mesh object names.")
    try:
        import bpy

        objects = []
        missing = []
        for name in object_names:
            obj, error = _mesh_object(bpy, name)
            if error:
                missing.append(name)
            else:
                objects.append(obj)
        if missing:
            return skill_error("Object not found", f"Missing or non-mesh object(s): {', '.join(missing)}")
        if len(objects) < 2:
            return skill_error("Need at least two meshes", "combine_meshes requires two or more mesh objects.")

        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        bpy.ops.object.join()
        combined = bpy.context.view_layer.objects.active or objects[0]
        if new_name:
            combined.name = new_name
            if getattr(combined, "data", None) is not None:
                combined.data.name = new_name
        return skill_success(
            f"Combined {len(objects)} mesh object(s)",
            source_objects=list(object_names),
            combined_count=len(objects),
            **_mesh_counts(combined),
            prompt="Use get_poly_count or get_bounding_box to inspect the combined mesh.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to combine meshes")


def merge_vertices(object_name: str, threshold: float = 0.0001) -> dict:
    """Merge nearby mesh vertices by distance."""
    if threshold < 0:
        return skill_error("Invalid threshold", "threshold must be non-negative.")
    try:
        import bpy

        obj, error = _mesh_object(bpy, object_name)
        if error:
            return error
        before = _mesh_counts(obj)
        _edit_select_all(bpy, obj)
        merge = getattr(bpy.ops.mesh, "merge_by_distance", None)
        remove = getattr(bpy.ops.mesh, "remove_doubles", None)
        if callable(merge):
            _call_mesh_operator(merge, distance=threshold)
        elif callable(remove):
            _call_mesh_operator(remove, threshold=threshold)
        else:
            return skill_error(
                "Merge operator unavailable", "Neither merge_by_distance nor remove_doubles is available."
            )
        _return_object_mode(bpy)
        after = _mesh_counts(obj)
        return skill_success(
            f"Merged vertices on {obj.name}",
            object_name=obj.name,
            threshold=threshold,
            before=before,
            after=after,
            prompt="Use get_poly_count to inspect the merged mesh.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        _safe_object_mode()
        return skill_exception(exc, message=f"Failed to merge vertices on {object_name}")


def extract_faces(object_name: str, face_indices: Sequence[int], new_name: str | None = None) -> dict:
    """Separate selected face indices into a new object."""
    if not face_indices or isinstance(face_indices, str):
        return skill_error("Invalid face_indices", "face_indices must be a non-empty list of polygon indices.")
    try:
        import bpy

        obj, error = _mesh_object(bpy, object_name)
        if error:
            return error
        polygons = list(obj.data.polygons)
        invalid = [index for index in face_indices if index < 0 or index >= len(polygons)]
        if invalid:
            return skill_error("Invalid face index", f"Out-of-range face index/indices: {invalid}")

        before_names = {obj.name for obj in bpy.data.objects}
        _select_active(bpy, obj)
        for poly in polygons:
            poly.select = int(poly.index) in set(face_indices)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.separate(type="SELECTED")
        _return_object_mode(bpy)
        after_names = {obj.name for obj in bpy.data.objects}
        created = sorted(after_names - before_names)
        if new_name and created:
            new_obj = bpy.data.objects.get(created[0])
            if new_obj is not None:
                old = new_obj.name
                new_obj.name = new_name
                if getattr(new_obj, "data", None) is not None:
                    new_obj.data.name = new_name
                created = [new_name if name == old else name for name in created]
        return skill_success(
            f"Extracted {len(face_indices)} face(s) from {object_name}",
            object_name=object_name,
            face_indices=list(face_indices),
            created_objects=created,
            created_count=len(created),
            prompt="Use get_poly_count on the returned object to inspect extracted topology.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        _safe_object_mode()
        return skill_exception(exc, message=f"Failed to extract faces from {object_name}")


def mirror_mesh(object_name: str, axis: str = "x", use_modifier: bool = True) -> dict:
    """Mirror a mesh by adding, and optionally applying, a Mirror modifier."""
    axis_key = axis.lower()
    if axis_key not in _MIRROR_AXES:
        return skill_error("Invalid mirror axis", "axis must be one of: x, y, z.")
    try:
        import bpy

        obj, error = _mesh_object(bpy, object_name)
        if error:
            return error
        _select_active(bpy, obj)
        modifier = obj.modifiers.new(name=f"Mirror_{axis_key.upper()}", type="MIRROR")
        axes = [False, False, False]
        axes[_MIRROR_AXES[axis_key]] = True
        modifier.use_axis = axes
        modifier_name = modifier.name
        applied = False
        if not use_modifier:
            bpy.ops.object.modifier_apply(modifier=modifier_name)
            applied = True
        return skill_success(
            f"Mirrored mesh {obj.name} on {axis_key.upper()}",
            object_name=obj.name,
            axis=axis_key,
            modifier_name=modifier_name,
            applied=applied,
            prompt="Use get_poly_count or list_modifiers to inspect the mirrored mesh.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to mirror mesh {object_name}")


def select_by_material(object_name: str, material_name: str) -> dict:
    """Select mesh faces assigned to a material."""
    if not material_name or not material_name.strip():
        return skill_error("Invalid material_name", "material_name must be a non-empty string.")
    try:
        import bpy

        obj, error = _mesh_object(bpy, object_name)
        if error:
            return error
        materials = list(getattr(obj.data, "materials", []))
        material_index = next(
            (idx for idx, mat in enumerate(materials) if getattr(mat, "name", None) == material_name), None
        )
        if material_index is None:
            return skill_error(
                f"Material not found: {material_name}", f"{object_name} has no material named '{material_name}'."
            )
        _select_active(bpy, obj)
        selected = 0
        for poly in obj.data.polygons:
            is_match = int(getattr(poly, "material_index", -1)) == material_index
            poly.select = is_match
            if is_match:
                selected += 1
        bpy.ops.object.mode_set(mode="EDIT")
        return skill_success(
            f"Selected {selected} face(s) using material {material_name}",
            object_name=obj.name,
            material_name=material_name,
            material_index=material_index,
            selected_face_count=selected,
            prompt="Use extract_faces or mesh editing tools on the selected faces.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        _safe_object_mode()
        return skill_exception(exc, message=f"Failed to select faces by material on {object_name}")


def _safe_object_mode() -> None:
    try:
        import bpy

        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass
