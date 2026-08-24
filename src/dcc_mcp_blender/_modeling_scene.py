"""Verified object, hierarchy, material, and UV modeling verbs."""

from __future__ import annotations

from typing import Optional, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._modeling_common import close, coords, mesh_object, select_object, uv_state, vector


def set_pivot(object_name: str, position: Sequence[float]) -> dict:
    """Move the object origin to an exact world-space position and verify it."""
    position_value, error = vector(position, "position")
    if error:
        return error
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        select_object(bpy, obj)
        cursor = bpy.context.scene.cursor
        previous = coords(cursor.location)
        try:
            cursor.location = position_value
            bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="MEDIAN")
            actual = coords(obj.matrix_world.translation)
        finally:
            cursor.location = previous
        if not close(actual, position_value):
            return skill_error(f"Pivot readback failed: {object_name}", "Object origin did not match the request.")
        return skill_success(
            f"Set pivot for {object_name}",
            object_name=obj.name,
            parameters={"position": position_value},
            readback={"position": actual, "verified": True},
            prompt="Use get_object_info to inspect the object transform.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set pivot for {object_name}")


def group_parent(
    object_names: Sequence[str],
    group_name: str,
    parent_name: Optional[str] = None,
) -> dict:
    """Link named objects to a collection and optionally parent them, with readback."""
    if isinstance(object_names, (str, bytes)) or not object_names or len(object_names) > 128:
        return skill_error("Invalid object_names", "Provide between 1 and 128 object names.")
    if any(not isinstance(name, str) or not name.strip() for name in object_names):
        return skill_error("Invalid object_names", "Every object name must be a non-empty string.")
    if len(set(object_names)) != len(object_names):
        return skill_error("Invalid object_names", "object_names must be unique.")
    if not isinstance(group_name, str) or not group_name.strip() or len(group_name) > 255:
        return skill_error("Invalid group_name", "group_name must contain between 1 and 255 characters.")
    try:
        import bpy

        objects = []
        missing = []
        for name in object_names:
            obj = bpy.data.objects.get(name)
            if obj is None:
                missing.append(name)
            else:
                objects.append(obj)
        if missing:
            return skill_error("Object not found", f"Missing object(s): {', '.join(missing)}")
        parent = None
        if parent_name:
            parent = bpy.data.objects.get(parent_name)
            if parent is None:
                return skill_error(f"Parent not found: {parent_name}", f"No object named '{parent_name}'.")
            if parent in objects:
                return skill_error("Invalid parent", "parent_name cannot also appear in object_names.")
        collection = bpy.data.collections.get(group_name)
        created = False
        if collection is None:
            collection = bpy.data.collections.new(group_name)
            created = True
            try:
                bpy.context.scene.collection.children.link(collection)
            except Exception:
                pass
        for obj in objects:
            if obj not in collection.objects:
                collection.objects.link(obj)
            if parent is not None:
                matrix_world = getattr(obj, "matrix_world", None)
                obj.parent = parent
                if matrix_world is not None:
                    try:
                        obj.matrix_world = matrix_world
                    except Exception:
                        pass
        members = [obj.name for obj in objects if obj in collection.objects]
        parented = [obj.name for obj in objects if getattr(obj, "parent", None) is parent] if parent else []
        verified = members == [obj.name for obj in objects] and (
            parent is None or parented == [obj.name for obj in objects]
        )
        if not verified:
            return skill_error(f"Group readback failed: {group_name}", "Collection or parent state did not match.")
        return skill_success(
            f"Grouped {len(objects)} object(s) into {group_name}",
            parameters={"group_name": group_name, "object_names": list(object_names), "parent_name": parent_name},
            readback={
                "collection_created": created,
                "group_name": collection.name,
                "members": members,
                "parent_name": getattr(parent, "name", None),
                "parented": parented,
                "verified": True,
            },
            prompt="Use collection and object inspection tools to inspect the hierarchy.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to group objects into {group_name}")


def freeze_transforms(
    object_name: str,
    location: bool = False,
    rotation: bool = True,
    scale: bool = True,
) -> dict:
    """Apply selected transforms and require neutral host values afterward."""
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        select_object(bpy, obj)
        before = {
            "location": coords(obj.location),
            "rotation": coords(obj.rotation_euler),
            "scale": coords(obj.scale),
        }
        bpy.ops.object.transform_apply(location=bool(location), rotation=bool(rotation), scale=bool(scale))
        after = {
            "location": coords(obj.location),
            "rotation": coords(obj.rotation_euler),
            "scale": coords(obj.scale),
        }
        verified = (
            (not location or close(after["location"], [0.0, 0.0, 0.0]))
            and (not rotation or close(after["rotation"], [0.0, 0.0, 0.0]))
            and (not scale or close(after["scale"], [1.0, 1.0, 1.0]))
        )
        if not verified:
            return skill_error(f"Transform readback failed: {object_name}", "Applied transforms were not neutral.")
        return skill_success(
            f"Froze transforms for {object_name}",
            object_name=obj.name,
            parameters={"location": bool(location), "rotation": bool(rotation), "scale": bool(scale)},
            readback={**after, "before": before, "verified": True},
            prompt="Use get_object_info to inspect the neutral transforms.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to freeze transforms for {object_name}")


def assign_material(object_name: str, material_name: str, slot_index: int = 0) -> dict:
    """Assign a material slot and require exact host connection readback."""
    if not isinstance(slot_index, int) or isinstance(slot_index, bool) or not 0 <= slot_index <= 63:
        return skill_error("Invalid slot_index", "slot_index must be an integer between 0 and 63.")
    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        material = bpy.data.materials.get(material_name)
        if material is None:
            return skill_error(f"Material not found: {material_name}", f"No material named '{material_name}'.")
        select_object(bpy, obj)
        while len(obj.material_slots) <= slot_index:
            bpy.ops.object.material_slot_add()
        obj.material_slots[slot_index].material = material
        actual = obj.material_slots[slot_index].material
        verified = actual is material or getattr(actual, "name", None) == material_name
        if not verified:
            return skill_error(f"Material readback failed: {object_name}", "Material slot did not retain the request.")
        return skill_success(
            f"Assigned {material_name} to {object_name}",
            parameters={"material_name": material_name, "object_name": object_name, "slot_index": slot_index},
            readback={
                "material_name": getattr(actual, "name", material_name),
                "object_name": obj.name,
                "slot_index": slot_index,
                "verified": True,
            },
            prompt="Use material inspection tools to verify shader connections.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to assign material to {object_name}")


def auto_uv(object_name: str, margin: float = 0.001) -> dict:
    """Run Blender smart projection and require UV-map readback."""
    from dcc_mcp_blender._uv_ops import unwrap_uvs

    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        before_state = uv_state(obj)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    result = unwrap_uvs(object_name=object_name, method="smart", margin=margin)
    if not result.get("success"):
        return result
    readback = uv_state(obj)
    if (
        readback["uv_map_count"] < 1
        or readback["uv_coordinate_count"] < 1
        or not readback["active_uv_map"]
        or readback["uv_digest"] == before_state["uv_digest"]
    ):
        return skill_error(
            f"UV readback failed: {object_name}",
            "Blender did not prove changed positive UV coordinates.",
            mutation_applied=True,
            rollback_attempted=False,
            rollback_verified=False,
            uv_before=before_state,
            uv_after=readback,
        )
    return skill_success(
        f"Generated smart UVs on {object_name}",
        object_name=object_name,
        parameters={"margin": float(margin), "projection": "smart"},
        readback={**readback, "verified": True},
        prompt="Use get_uv_islands or pack_uvs to inspect the generated UVs.",
    )


def uv_project(
    object_name: str,
    projection: str = "planar",
    axis: str = "z",
    margin: float = 0.0,
) -> dict:
    """Project UVs through the existing typed UV owner and verify readback."""
    projection_key = str(projection).lower()
    methods = {"planar": "planar", "cylindrical": "cylinder", "spherical": "sphere", "cube": "cube"}
    if projection_key not in methods:
        return skill_error("Invalid projection", "projection must be planar, cylindrical, spherical, or cube.")
    from dcc_mcp_blender._uv_ops import project_uvs

    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        before_state = uv_state(obj)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    result = project_uvs(object_name=object_name, method=methods[projection_key], axis=axis, margin=margin)
    if not result.get("success"):
        return result
    readback = uv_state(obj)
    if (
        readback["uv_map_count"] < 1
        or readback["uv_coordinate_count"] < 1
        or not readback["active_uv_map"]
        or readback["uv_digest"] == before_state["uv_digest"]
    ):
        return skill_error(
            f"UV readback failed: {object_name}",
            "Blender did not prove changed positive UV coordinates.",
            mutation_applied=True,
            rollback_attempted=False,
            rollback_verified=False,
            uv_before=before_state,
            uv_after=readback,
        )
    return skill_success(
        f"Projected {projection_key} UVs on {object_name}",
        object_name=object_name,
        parameters={"axis": str(axis).lower(), "margin": float(margin), "projection": projection_key},
        readback={**readback, "verified": True},
        prompt="Use get_uv_islands or pack_uvs to inspect the projected UVs.",
    )
