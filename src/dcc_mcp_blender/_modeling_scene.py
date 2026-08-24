"""Verified object, hierarchy, material, and UV modeling verbs."""

from __future__ import annotations

from typing import Optional, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._modeling_common import (
    close,
    coords,
    mesh_object,
    object_identity,
    operator_finished,
    post_mutation_uv_state,
    select_object,
    uv_state,
    vector,
)


def _contains_identity(items, target) -> bool:
    """Compare Blender wrappers by stable host identity rather than Python wrapper identity."""
    target_identity = object_identity(target)
    return any(object_identity(item) == target_identity for item in items)


def _rollback_group_changes(bpy, collection, created, scene_linked, newly_linked, original_parents) -> bool:
    """Best-effort rollback for collection linking and parenting changes."""
    for obj, original_parent in original_parents:
        try:
            obj.parent = original_parent
        except Exception:
            pass
    unlink = getattr(collection.objects, "unlink", None)
    for obj in newly_linked:
        try:
            if callable(unlink):
                unlink(obj)
            elif obj in collection.objects:
                collection.objects.remove(obj)
        except Exception:
            pass
    scene_children = bpy.context.scene.collection.children
    if created:
        try:
            if scene_linked:
                scene_unlink = getattr(scene_children, "unlink", None)
                if callable(scene_unlink):
                    scene_unlink(collection)
                elif collection in scene_children:
                    scene_children.remove(collection)
        except Exception:
            pass
        try:
            bpy.data.collections.remove(collection)
        except Exception:
            pass
    collection_absent = not created or not _contains_identity(bpy.data.collections, collection)
    members_restored = all(not _contains_identity(collection.objects, obj) for obj in newly_linked)
    parents_restored = all(
        object_identity(getattr(obj, "parent", None)) == object_identity(original_parent)
        if original_parent is not None
        else getattr(obj, "parent", None) is None
        for obj, original_parent in original_parents
    )
    return collection_absent and members_restored and parents_restored


def set_pivot(object_name: str, position: Sequence[float]) -> dict:
    """Move the object origin to an exact world-space position and verify it."""
    obj = None
    before = None
    operation_started = False
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
        before = coords(obj.matrix_world.translation)
        try:
            cursor.location = position_value
            operation_started = True
            finished = operator_finished(bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="MEDIAN"))
            actual = coords(obj.matrix_world.translation)
        finally:
            cursor.location = previous
        if not finished:
            return skill_error(
                f"Pivot operation failed: {object_name}",
                "Blender did not report FINISHED for origin_set.",
                mutation_applied=not close(before, actual),
                rollback_attempted=False,
                rollback_verified=False,
                position_before=before,
                position_after=actual,
            )
        if not close(actual, position_value):
            return skill_error(
                f"Pivot readback failed: {object_name}",
                "Object origin did not match the request.",
                mutation_applied=not close(before, actual),
                rollback_attempted=False,
                rollback_verified=False,
                position_before=before,
                position_after=actual,
            )
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
        if obj is not None and operation_started:
            try:
                actual = coords(obj.matrix_world.translation)
            except Exception:
                actual = None
            return skill_error(
                f"Pivot verification failed: {object_name}",
                "The origin operation may have mutated the object before verification failed.",
                mutation_applied=True,
                rollback_attempted=False,
                rollback_verified=False,
                error_type=type(exc).__name__,
                position_before=before,
                position_after=actual,
            )
        return skill_exception(exc, message=f"Failed to set pivot for {object_name}")


def group_parent(
    object_names: Sequence[str],
    group_name: str,
    parent_name: Optional[str] = None,
) -> dict:
    """Link named objects to a collection and optionally parent them, with readback."""
    collection = None
    created = False
    scene_linked = False
    newly_linked = []
    original_parents = []
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
            if any(object_identity(obj) == object_identity(parent) for obj in objects):
                return skill_error("Invalid parent", "parent_name cannot also appear in object_names.")
        collection = bpy.data.collections.get(group_name)
        scene_children = bpy.context.scene.collection.children
        if collection is None:
            collection = bpy.data.collections.new(group_name)
            created = True
            try:
                scene_children.link(collection)
            except Exception as exc:
                rollback_verified = _rollback_group_changes(bpy, collection, created, False, [], [])
                return skill_error(
                    f"Group scene link failed: {group_name}",
                    "The new collection could not be linked into the active scene.",
                    mutation_applied=True,
                    rollback_attempted=True,
                    rollback_verified=rollback_verified,
                    error_type=type(exc).__name__,
                    collection_created=True,
                    scene_linked=False,
                )
        scene_linked = _contains_identity(scene_children, collection)
        if not scene_linked:
            rollback_verified = _rollback_group_changes(bpy, collection, created, False, [], [])
            return skill_error(
                f"Group scene link failed: {group_name}",
                "The collection is not linked into the active scene.",
                mutation_applied=created,
                rollback_attempted=created,
                rollback_verified=rollback_verified if created else False,
                collection_created=created,
                scene_linked=False,
            )
        for obj in objects:
            if not _contains_identity(collection.objects, obj):
                try:
                    collection.objects.link(obj)
                except Exception:
                    if _contains_identity(collection.objects, obj):
                        newly_linked.append(obj)
                    raise
                if _contains_identity(collection.objects, obj):
                    newly_linked.append(obj)
            if parent is not None:
                matrix_world = getattr(obj, "matrix_world", None)
                original_parent = getattr(obj, "parent", None)
                original_parents.append((obj, original_parent))
                obj.parent = parent
                if matrix_world is not None:
                    try:
                        obj.matrix_world = matrix_world
                    except Exception:
                        pass
        members = [obj.name for obj in objects if _contains_identity(collection.objects, obj)]
        parented = (
            [
                obj.name
                for obj in objects
                if getattr(obj, "parent", None) is not None
                and object_identity(getattr(obj, "parent", None)) == object_identity(parent)
            ]
            if parent
            else []
        )
        verified = members == [obj.name for obj in objects] and (
            parent is None or parented == [obj.name for obj in objects]
        )
        if not verified:
            rollback_verified = _rollback_group_changes(
                bpy, collection, created, scene_linked, newly_linked, original_parents
            )
            return skill_error(
                f"Group readback failed: {group_name}",
                "Collection or parent state did not match.",
                mutation_applied=bool(created or newly_linked or original_parents),
                rollback_attempted=True,
                rollback_verified=rollback_verified,
                collection_created=created,
                scene_linked=scene_linked,
                members=members,
                parented=parented,
            )
        return skill_success(
            f"Grouped {len(objects)} object(s) into {group_name}",
            parameters={"group_name": group_name, "object_names": list(object_names), "parent_name": parent_name},
            readback={
                "collection_created": created,
                "group_name": collection.name,
                "members": members,
                "parent_name": getattr(parent, "name", None),
                "parented": parented,
                "scene_linked": scene_linked,
                "verified": True,
            },
            prompt="Use collection and object inspection tools to inspect the hierarchy.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        if collection is not None and (created or newly_linked or original_parents):
            rollback_verified = _rollback_group_changes(
                bpy, collection, created, scene_linked, newly_linked, original_parents
            )
            return skill_error(
                f"Group operation failed: {group_name}",
                "Partial collection or parent changes were rolled back where possible.",
                mutation_applied=True,
                rollback_attempted=True,
                rollback_verified=rollback_verified,
                error_type=type(exc).__name__,
                collection_created=created,
                scene_linked=scene_linked,
                linked_objects=[getattr(obj, "name", None) for obj in newly_linked],
                parented_objects=[getattr(obj, "name", None) for obj, _ in original_parents],
            )
        return skill_exception(exc, message=f"Failed to group objects into {group_name}")


def freeze_transforms(
    object_name: str,
    location: bool = False,
    rotation: bool = True,
    scale: bool = True,
) -> dict:
    """Apply selected transforms and require neutral host values afterward."""
    obj = None
    before = None
    operation_started = False
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
        operation_started = True
        finished = operator_finished(
            bpy.ops.object.transform_apply(location=bool(location), rotation=bool(rotation), scale=bool(scale))
        )
        after = {
            "location": coords(obj.location),
            "rotation": coords(obj.rotation_euler),
            "scale": coords(obj.scale),
        }
        if not finished:
            return skill_error(
                f"Transform operation failed: {object_name}",
                "Blender did not report FINISHED for transform_apply.",
                mutation_applied=after != before,
                rollback_attempted=False,
                rollback_verified=False,
                transform_before=before,
                transform_after=after,
            )
        verified = (
            (not location or close(after["location"], [0.0, 0.0, 0.0]))
            and (not rotation or close(after["rotation"], [0.0, 0.0, 0.0]))
            and (not scale or close(after["scale"], [1.0, 1.0, 1.0]))
        )
        if not verified:
            return skill_error(
                f"Transform readback failed: {object_name}",
                "Applied transforms were not neutral.",
                mutation_applied=after != before,
                rollback_attempted=False,
                rollback_verified=False,
                transform_before=before,
                transform_after=after,
            )
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
        if obj is not None and operation_started:
            try:
                after = {
                    "location": coords(obj.location),
                    "rotation": coords(obj.rotation_euler),
                    "scale": coords(obj.scale),
                }
            except Exception:
                after = None
            return skill_error(
                f"Transform verification failed: {object_name}",
                "The transform operation may have mutated the object before verification failed.",
                mutation_applied=True,
                rollback_attempted=False,
                rollback_verified=False,
                error_type=type(exc).__name__,
                transform_before=before,
                transform_after=after,
            )
        return skill_exception(exc, message=f"Failed to freeze transforms for {object_name}")


def _rollback_material_slots(bpy, obj, initial_slot_count: int, slot_index: int, previous_material) -> bool:
    """Restore an existing assignment and remove only slots appended by this call."""
    if slot_index < initial_slot_count:
        try:
            obj.material_slots[slot_index].material = previous_material
        except Exception:
            pass
    while len(obj.material_slots) > initial_slot_count:
        before = len(obj.material_slots)
        try:
            obj.active_material_index = before - 1
            result = bpy.ops.object.material_slot_remove()
        except Exception:
            break
        if not operator_finished(result) or len(obj.material_slots) >= before:
            break
    assignment_restored = True
    if slot_index < initial_slot_count:
        actual = obj.material_slots[slot_index].material
        assignment_restored = actual is previous_material or (
            getattr(actual, "name", None) == getattr(previous_material, "name", None)
        )
    return len(obj.material_slots) == initial_slot_count and assignment_restored


def assign_material(object_name: str, material_name: str, slot_index: int = 0) -> dict:
    """Assign a material slot and require exact host connection readback."""
    obj = None
    initial_slot_count = None
    previous_material = None
    assignment_attempted = False
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
        initial_slot_count = len(obj.material_slots)
        while len(obj.material_slots) <= slot_index:
            before_slot_count = len(obj.material_slots)
            finished = operator_finished(bpy.ops.object.material_slot_add())
            after_slot_count = len(obj.material_slots)
            if not finished or after_slot_count <= before_slot_count:
                rollback_verified = _rollback_material_slots(
                    bpy, obj, initial_slot_count, slot_index, previous_material
                )
                return skill_error(
                    f"Material slot creation failed: {object_name}",
                    "Blender did not create the requested material slot.",
                    mutation_applied=after_slot_count != initial_slot_count,
                    rollback_attempted=after_slot_count != initial_slot_count,
                    rollback_verified=rollback_verified,
                    slot_count_before=initial_slot_count,
                    slot_count_after=after_slot_count,
                )
        previous_material = obj.material_slots[slot_index].material
        assignment_attempted = True
        obj.material_slots[slot_index].material = material
        actual = obj.material_slots[slot_index].material
        verified = actual is material or getattr(actual, "name", None) == material_name
        if not verified:
            rollback_verified = _rollback_material_slots(bpy, obj, initial_slot_count, slot_index, previous_material)
            return skill_error(
                f"Material readback failed: {object_name}",
                "Material slot did not retain the request.",
                mutation_applied=True,
                rollback_attempted=True,
                rollback_verified=rollback_verified,
                slot_count_before=initial_slot_count,
                slot_count_after=len(obj.material_slots),
            )
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
        if (
            obj is not None
            and initial_slot_count is not None
            and (assignment_attempted or len(obj.material_slots) != initial_slot_count)
        ):
            mutated_slot_count = len(obj.material_slots)
            rollback_verified = _rollback_material_slots(bpy, obj, initial_slot_count, slot_index, previous_material)
            return skill_error(
                f"Material assignment failed: {object_name}",
                "Material slots changed before the assignment failed and were rolled back where possible.",
                mutation_applied=True,
                rollback_attempted=True,
                rollback_verified=rollback_verified,
                error_type=type(exc).__name__,
                slot_count_before=initial_slot_count,
                slot_count_after=mutated_slot_count,
            )
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
    readback, evidence_error = post_mutation_uv_state("Auto UV", obj, before_state)
    if evidence_error:
        return evidence_error
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
    axis_key = str(axis).lower()
    methods = {"planar": "planar", "cylindrical": "cylinder", "spherical": "sphere", "cube": "cube"}
    if projection_key not in methods:
        return skill_error("Invalid projection", "projection must be planar, cylindrical, spherical, or cube.")
    if axis_key not in {"x", "y", "z"}:
        return skill_error("Invalid axis", "axis must be one of: x, y, z.")
    if projection_key != "planar" and axis_key != "z":
        return skill_error(
            "Invalid axis for projection",
            "axis controls planar projection only; use the z sentinel for cylindrical, spherical, and cube modes.",
        )
    from dcc_mcp_blender._uv_ops import project_uvs

    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        before_state = uv_state(obj)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    result = project_uvs(object_name=object_name, method=methods[projection_key], axis=axis_key, margin=margin)
    if not result.get("success"):
        return result
    readback, evidence_error = post_mutation_uv_state("UV projection", obj, before_state)
    if evidence_error:
        return evidence_error
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
        parameters={
            "axis": axis_key if projection_key == "planar" else None,
            "margin": float(margin),
            "projection": projection_key,
        },
        readback={**readback, "verified": True},
        prompt="Use get_uv_islands or pack_uvs to inspect the projected UVs.",
    )
