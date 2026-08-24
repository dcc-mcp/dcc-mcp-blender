"""Verified primitive, loft, and lathe creation for typed Blender modeling."""

from __future__ import annotations

import math
from typing import Optional, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._modeling_common import (
    AXIS_INDEX,
    active_object,
    close,
    coords,
    duplicate_mesh,
    mesh_counts,
    mesh_object,
    object_identity,
    object_mode,
    object_mode_if_available,
    operator_finished,
    remove_object,
    select_object,
    vector,
)

_PRIMITIVE_OPERATORS = {
    "cube": "primitive_cube_add",
    "sphere": "primitive_uv_sphere_add",
    "ico_sphere": "primitive_ico_sphere_add",
    "cylinder": "primitive_cylinder_add",
    "cone": "primitive_cone_add",
    "torus": "primitive_torus_add",
    "plane": "primitive_plane_add",
    "circle": "primitive_circle_add",
}


def create_primitive(
    primitive_type: str,
    name: str,
    location: Sequence[float] = (0.0, 0.0, 0.0),
    rotation: Sequence[float] = (0.0, 0.0, 0.0),
    scale: Sequence[float] = (1.0, 1.0, 1.0),
    size: float = 1.0,
) -> dict:
    """Create a named primitive and verify its Blender transform readback."""
    kind = str(primitive_type).lower()
    if kind not in _PRIMITIVE_OPERATORS:
        return skill_error("Invalid primitive_type", f"Use one of: {', '.join(sorted(_PRIMITIVE_OPERATORS))}.")
    if not isinstance(name, str) or not name.strip() or len(name) > 255:
        return skill_error("Invalid name", "name must contain between 1 and 255 characters.")
    location_value, error = vector(location, "location")
    if error:
        return error
    rotation_value, error = vector(rotation, "rotation")
    if error:
        return error
    scale_value, error = vector(scale, "scale", positive=True)
    if error:
        return error
    try:
        size_value = float(size)
    except (TypeError, ValueError):
        return skill_error("Invalid size", "size must be numeric.")
    if not math.isfinite(size_value) or size_value <= 0 or size_value > 1_000_000:
        return skill_error("Invalid size", "size must be finite, greater than zero, and at most 1000000.")
    try:
        import bpy

        if bpy.data.objects.get(name) is not None:
            return skill_error(f"Object already exists: {name}", "Choose a unique semantic object name.")
        before_identities = {object_identity(existing) for existing in bpy.data.objects}
        rotation_radians = [math.radians(component) for component in rotation_value]
        kwargs = {"location": location_value, "rotation": rotation_radians}
        if kind in {"cube", "plane"}:
            kwargs["size"] = size_value
        elif kind in {"sphere", "ico_sphere", "circle"}:
            kwargs["radius"] = size_value / 2.0
        elif kind == "cylinder":
            kwargs.update({"radius": size_value / 2.0, "depth": size_value})
        elif kind == "cone":
            kwargs.update({"radius1": size_value / 2.0, "depth": size_value})
        elif kind == "torus":
            kwargs.update({"major_radius": size_value / 2.0, "minor_radius": size_value / 8.0})
        operator_result = getattr(bpy.ops.mesh, _PRIMITIVE_OPERATORS[kind])(**kwargs)
        obj = active_object(bpy)
        if obj is None or object_identity(obj) in before_identities or getattr(obj, "type", None) != "MESH":
            return skill_error("Primitive creation failed", "Blender did not expose the created mesh as active.")
        if not operator_finished(operator_result):
            remove_object(bpy, obj)
            remaining_identities = {object_identity(existing) for existing in bpy.data.objects}
            return skill_error(
                "Primitive creation failed",
                "Blender did not report a finished primitive operation.",
                mutation_applied=True,
                rollback_attempted=True,
                rollback_verified=object_identity(obj) not in remaining_identities,
            )
        obj.name = name
        if getattr(obj, "data", None) is not None:
            obj.data.name = name
        obj.scale = scale_value
        actual_location = coords(obj.location)
        actual_rotation = [math.degrees(component) for component in coords(obj.rotation_euler)]
        actual_scale = coords(obj.scale)
        counts = mesh_counts(obj)
        verified = (
            obj.name == name
            and getattr(obj, "type", None) == "MESH"
            and counts["vertex_count"] > 0
            and close(actual_location, location_value)
            and close(actual_rotation, rotation_value)
            and close(actual_scale, scale_value)
        )
        if not verified:
            remove_object(bpy, obj)
            return skill_error(
                f"Primitive readback failed: {name}", "Blender state did not match the requested transform."
            )
        return skill_success(
            f"Created {kind} primitive {name}",
            parameters={
                "primitive_type": kind,
                "name": name,
                "location": location_value,
                "rotation": rotation_value,
                "scale": scale_value,
                "size": size_value,
            },
            readback={
                "location": actual_location,
                "name": obj.name,
                "rotation": actual_rotation,
                "scale": actual_scale,
                "type": obj.type,
                **counts,
                "verified": True,
            },
            prompt="Use get_poly_count or get_bounding_box to inspect the primitive.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create {kind} primitive")


def loft_sections(sections: Sequence[str], output_name: Optional[str] = None) -> dict:
    """Bridge ordered mesh-loop copies while preserving the source sections."""
    if isinstance(sections, (str, bytes)) or not 2 <= len(sections) <= 64:
        return skill_error("Invalid sections", "Provide between 2 and 64 section object names.")
    if any(not isinstance(name, str) or not name.strip() for name in sections) or len(set(sections)) != len(sections):
        return skill_error("Invalid sections", "Section names must be non-empty and unique.")
    target_name = output_name or "Loft"
    if not isinstance(target_name, str) or not target_name.strip() or len(target_name) > 255:
        return skill_error("Invalid output_name", "output_name must contain between 1 and 255 characters.")
    copies = []
    try:
        import bpy

        if bpy.data.objects.get(target_name) is not None:
            return skill_error(f"Object already exists: {target_name}", "Choose a unique output_name.")
        sources = []
        vertex_counts = set()
        for name in sections:
            source, error = mesh_object(bpy, name)
            if error:
                return error
            if len(source.data.edges) < 3:
                return skill_error(f"Invalid loft section: {name}", "Each section needs at least three edges.")
            sources.append(source)
            vertex_counts.add(len(source.data.vertices))
        if len(vertex_counts) != 1:
            return skill_error("Incompatible loft sections", "Every section must have the same vertex count.")
        copies = [duplicate_mesh(bpy, source, f"__dcc_mcp_loft_{index}") for index, source in enumerate(sources)]
        object_mode(bpy)
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except Exception:
            pass
        for duplicate in copies:
            duplicate.select_set(True)
        joined = copies[0]
        bpy.context.view_layer.objects.active = joined
        bpy.ops.object.join()
        joined.name = target_name
        joined.data.name = target_name
        before = mesh_counts(joined)
        bpy.ops.object.mode_set(mode="EDIT")
        select_mode = getattr(bpy.ops.mesh, "select_mode", None)
        if callable(select_mode):
            select_mode(type="EDGE")
        bpy.ops.mesh.select_all(action="SELECT")
        try:
            bpy.ops.mesh.bridge_edge_loops(type="OPEN", number_cuts=0, interpolation="LINEAR")
        except TypeError:
            bpy.ops.mesh.bridge_edge_loops()
        object_mode(bpy)
        after = mesh_counts(joined)
        if after["face_count"] <= before["face_count"]:
            remove_object(bpy, joined)
            return skill_error("Loft had no verifiable effect", "Blender reported no new bridge faces.")
        return skill_success(
            f"Lofted {len(sources)} sections into {target_name}",
            parameters={"output_name": target_name, "sections": list(sections)},
            readback={
                **after,
                "object_name": joined.name,
                "source_objects": [source.name for source in sources],
                "verified": True,
            },
            prompt="Use get_poly_count to inspect the lofted mesh.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        try:
            import bpy

            for duplicate in copies:
                remove_object(bpy, duplicate)
        except Exception:
            pass
        object_mode_if_available()
        return skill_exception(exc, message="Failed to loft sections")


def lathe_profile(
    profile: str,
    axis: str = "y",
    origin: Sequence[float] = (0.0, 0.0, 0.0),
    segments: int = 32,
    output_name: Optional[str] = None,
) -> dict:
    """Revolve a profile copy through Blender's native Screw modifier."""
    axis_key = str(axis).lower()
    if axis_key not in AXIS_INDEX:
        return skill_error("Invalid axis", "axis must be one of: x, y, z.")
    if not isinstance(segments, int) or isinstance(segments, bool) or not 3 <= segments <= 256:
        return skill_error("Invalid segments", "segments must be an integer between 3 and 256.")
    origin_value, error = vector(origin, "origin")
    if error:
        return error
    target_name = output_name or f"{profile}_Lathe"
    if not isinstance(target_name, str) or not target_name.strip() or len(target_name) > 255:
        return skill_error("Invalid output_name", "output_name must contain between 1 and 255 characters.")
    duplicate = None
    try:
        import bpy

        source, error = mesh_object(bpy, profile)
        if error:
            return error
        if len(source.data.vertices) < 2 or len(source.data.edges) < 1:
            return skill_error(
                f"Invalid profile: {profile}", "A lathe profile needs at least two vertices and one edge."
            )
        if bpy.data.objects.get(target_name) is not None:
            return skill_error(f"Object already exists: {target_name}", "Choose a unique output_name.")
        duplicate = duplicate_mesh(bpy, source, target_name)
        select_object(bpy, duplicate)
        cursor = bpy.context.scene.cursor
        previous_cursor = coords(cursor.location)
        try:
            cursor.location = origin_value
            bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="MEDIAN")
        finally:
            cursor.location = previous_cursor
        if not close(coords(duplicate.matrix_world.translation), origin_value):
            remove_object(bpy, duplicate)
            return skill_error("Lathe origin readback failed", "Profile origin did not match the request.")
        before = mesh_counts(duplicate)
        modifier = duplicate.modifiers.new(name="Lathe_Profile", type="SCREW")
        modifier.axis = axis_key.upper()
        modifier.angle = math.tau
        modifier.steps = segments
        modifier.render_steps = segments
        modifier.use_merge_vertices = True
        configured = (
            str(modifier.axis) == axis_key.upper()
            and int(modifier.steps) == segments
            and int(modifier.render_steps) == segments
            and abs(float(modifier.angle) - math.tau) <= 1e-6
        )
        if not configured:
            remove_object(bpy, duplicate)
            return skill_error("Lathe modifier readback failed", "Screw modifier did not retain the request.")
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        after = mesh_counts(duplicate)
        if after["face_count"] <= before["face_count"]:
            remove_object(bpy, duplicate)
            return skill_error("Lathe had no verifiable effect", "Blender reported no generated faces.")
        return skill_success(
            f"Lathed {profile} into {target_name}",
            parameters={
                "axis": axis_key,
                "origin": origin_value,
                "output_name": target_name,
                "profile": profile,
                "segments": segments,
            },
            readback={**after, "object_name": duplicate.name, "verified": True},
            prompt="Use get_poly_count to inspect the revolved mesh.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        try:
            import bpy

            if duplicate is not None:
                remove_object(bpy, duplicate)
        except Exception:
            pass
        return skill_exception(exc, message=f"Failed to lathe profile {profile}")
