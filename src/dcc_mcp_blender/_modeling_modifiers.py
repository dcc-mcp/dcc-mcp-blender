"""Verified modifier-backed verbs for the shared modeling vocabulary."""

from __future__ import annotations

from typing import Optional, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._modeling_common import (
    AXIS_INDEX,
    close,
    coords,
    mesh_evidence_counts,
    mesh_object,
    mesh_state,
    object_identity,
    operator_finished,
    post_mutation_mesh_state,
    select_object,
    vector,
)

_BOOLEAN_OPERATIONS = {"union": "UNION", "intersect": "INTERSECT", "subtract": "DIFFERENCE"}


def _modifier_exception_receipt(bpy, obj, modifier, before_mesh, apply_attempted, exc, operation) -> dict:
    """Convert unexpected post-creation failures into a bounded mutation receipt."""
    modifier_name = str(getattr(modifier, "name", ""))
    if apply_attempted:
        try:
            after_counts = mesh_evidence_counts(obj)
        except Exception:
            after_counts = None
        return skill_error(
            f"{operation} verification failed: {obj.name}",
            "The host operation may have mutated the mesh before verification failed.",
            mutation_applied=True,
            rollback_attempted=False,
            rollback_verified=False,
            error_type=type(exc).__name__,
            modifier_name=modifier_name,
            mesh_before=before_mesh,
            mesh_after_counts=after_counts,
        )
    try:
        obj.modifiers.remove(modifier)
    except Exception:
        pass
    modifier_present = obj.modifiers.get(modifier_name) is not None
    return skill_error(
        f"{operation} configuration failed: {obj.name}",
        "The new modifier could not be verified and was rolled back where possible.",
        mutation_applied=modifier_present,
        rollback_attempted=True,
        rollback_verified=not modifier_present,
        error_type=type(exc).__name__,
        modifier_name=modifier_name,
    )


def array_instances(
    object_name: str,
    count: int,
    offset: Sequence[float],
    apply: bool = False,  # noqa: A002
    modifier_name: Optional[str] = None,
) -> dict:
    """Create a bounded constant-offset Array modifier with exact readback."""
    obj = None
    modifier = None
    before_mesh = None
    apply_attempted = False
    if not isinstance(count, int) or isinstance(count, bool) or not 2 <= count <= 128:
        return skill_error("Invalid count", "count must be an integer between 2 and 128.")
    offset_value, error = vector(offset, "offset")
    if error:
        return error
    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        if len(obj.modifiers) >= 128:
            return skill_error("Modifier limit reached", "Refuse to add more than 128 modifiers to one object.")
        before_mesh = mesh_state(obj)
        select_object(bpy, obj)
        modifier = obj.modifiers.new(name=modifier_name or "Array_Instances", type="ARRAY")
        modifier.count = count
        modifier.use_relative_offset = False
        modifier.use_constant_offset = True
        modifier.constant_offset_displace = offset_value
        name = modifier.name
        actual_configuration = {
            "count": int(modifier.count),
            "constant_offset": coords(modifier.constant_offset_displace),
            "use_constant_offset": bool(modifier.use_constant_offset),
            "use_relative_offset": bool(modifier.use_relative_offset),
        }
        configuration_verified = (
            actual_configuration["count"] == count
            and close(actual_configuration["constant_offset"], offset_value)
            and actual_configuration["use_constant_offset"]
            and not actual_configuration["use_relative_offset"]
        )
        if not configuration_verified:
            try:
                obj.modifiers.remove(modifier)
            except Exception:
                pass
            modifier_present = obj.modifiers.get(name) is not None
            return skill_error(
                f"Array configuration failed: {object_name}",
                "Blender did not retain the requested Array settings.",
                mutation_applied=modifier_present,
                rollback_attempted=True,
                rollback_verified=not modifier_present,
                requested_configuration={"count": count, "constant_offset": offset_value},
                actual_configuration=actual_configuration,
            )
        apply_finished = False
        if bool(apply):
            apply_attempted = True
            apply_finished = operator_finished(bpy.ops.object.modifier_apply(modifier=name))
        present = obj.modifiers.get(name) is not None
        after_mesh, evidence_error = post_mutation_mesh_state("Array", obj, before_mesh)
        if evidence_error:
            return evidence_error
        verified = (
            (not present and apply_finished and after_mesh["mesh_digest"] != before_mesh["mesh_digest"])
            if bool(apply)
            else (present and configuration_verified)
        )
        if not verified:
            context = {}
            if bool(apply):
                context = {
                    "mutation_applied": True,
                    "rollback_attempted": False,
                    "rollback_verified": False,
                    "mesh_before": before_mesh,
                    "mesh_after": after_mesh,
                }
            return skill_error(
                f"Array readback failed: {object_name}",
                "Modifier state or applied mesh did not match the request.",
                **context,
            )
        return skill_success(
            f"Created {count}-item array on {object_name}",
            object_name=obj.name,
            parameters={"apply": bool(apply), "count": count, "offset": offset_value},
            readback={
                "applied": bool(apply),
                "constant_offset": actual_configuration["constant_offset"],
                "count": actual_configuration["count"],
                "modifier_name": name,
                "modifier_type": "ARRAY",
                "verified": True,
                "mesh_before": before_mesh,
                "mesh_after": after_mesh,
            },
            prompt="Use list_modifiers or get_poly_count to inspect the array.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        if obj is not None and modifier is not None:
            return _modifier_exception_receipt(bpy, obj, modifier, before_mesh, apply_attempted, exc, "Array")
        return skill_exception(exc, message=f"Failed to array {object_name}")


def mirror(
    object_name: str,
    axis: str = "x",
    merge: bool = True,
    bisect: bool = False,
    apply: bool = False,  # noqa: A002
    modifier_name: Optional[str] = None,
) -> dict:
    """Create a typed Mirror modifier with exact axis/readback semantics."""
    obj = None
    modifier = None
    before_mesh = None
    apply_attempted = False
    axis_key = str(axis).lower()
    if axis_key not in AXIS_INDEX:
        return skill_error("Invalid axis", "axis must be one of: x, y, z.")
    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        if len(obj.modifiers) >= 128:
            return skill_error("Modifier limit reached", "Refuse to add more than 128 modifiers to one object.")
        before_mesh = mesh_state(obj)
        select_object(bpy, obj)
        modifier = obj.modifiers.new(name=modifier_name or f"Mirror_{axis_key.upper()}", type="MIRROR")
        axes = [False, False, False]
        axes[AXIS_INDEX[axis_key]] = True
        modifier.use_axis = axes
        modifier.use_bisect_axis = [bool(bisect) if enabled else False for enabled in axes]
        modifier.use_mirror_merge = bool(merge)
        name = modifier.name
        actual_configuration = {
            "use_axis": [bool(value) for value in modifier.use_axis],
            "use_bisect_axis": [bool(value) for value in modifier.use_bisect_axis],
            "use_mirror_merge": bool(modifier.use_mirror_merge),
        }
        expected_bisect_axes = [bool(bisect) if enabled else False for enabled in axes]
        configuration_verified = (
            actual_configuration["use_axis"] == axes
            and actual_configuration["use_bisect_axis"] == expected_bisect_axes
            and actual_configuration["use_mirror_merge"] == bool(merge)
        )
        if not configuration_verified:
            try:
                obj.modifiers.remove(modifier)
            except Exception:
                pass
            modifier_present = obj.modifiers.get(name) is not None
            return skill_error(
                f"Mirror configuration failed: {object_name}",
                "Blender did not retain the requested Mirror settings.",
                mutation_applied=modifier_present,
                rollback_attempted=True,
                rollback_verified=not modifier_present,
                requested_configuration={
                    "use_axis": axes,
                    "use_bisect_axis": expected_bisect_axes,
                    "use_mirror_merge": bool(merge),
                },
                actual_configuration=actual_configuration,
            )
        apply_finished = False
        if bool(apply):
            apply_attempted = True
            apply_finished = operator_finished(bpy.ops.object.modifier_apply(modifier=name))
        present = obj.modifiers.get(name) is not None
        after_mesh, evidence_error = post_mutation_mesh_state("Mirror", obj, before_mesh)
        if evidence_error:
            return evidence_error
        actual_axes = actual_configuration["use_axis"]
        verified = (
            (not present and apply_finished and after_mesh["mesh_digest"] != before_mesh["mesh_digest"])
            if bool(apply)
            else (present and configuration_verified)
        )
        if not verified:
            context = {}
            if bool(apply):
                context = {
                    "mutation_applied": True,
                    "rollback_attempted": False,
                    "rollback_verified": False,
                    "mesh_before": before_mesh,
                    "mesh_after": after_mesh,
                }
            return skill_error(
                f"Mirror readback failed: {object_name}",
                "Modifier state or applied mesh did not match the request.",
                **context,
            )
        return skill_success(
            f"Created {axis_key.upper()} mirror on {object_name}",
            object_name=obj.name,
            parameters={"apply": bool(apply), "axis": axis_key, "bisect": bool(bisect), "merge": bool(merge)},
            readback={
                "applied": bool(apply),
                "axis": axis_key,
                "bisect": bool(bisect),
                "merge": bool(merge),
                "modifier_name": name,
                "modifier_type": "MIRROR",
                "use_axis": actual_axes,
                "verified": True,
                "mesh_before": before_mesh,
                "mesh_after": after_mesh,
            },
            prompt="Use list_modifiers or get_poly_count to inspect the mirror.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        if obj is not None and modifier is not None:
            return _modifier_exception_receipt(bpy, obj, modifier, before_mesh, apply_attempted, exc, "Mirror")
        return skill_exception(exc, message=f"Failed to mirror {object_name}")


def boolean_op(
    input_a: str,
    input_b: str,
    operation: str,
    apply: bool = True,  # noqa: A002
    output_name: Optional[str] = None,
) -> dict:
    """Apply a typed two-object Boolean modifier and verify its host state."""
    left = None
    modifier = None
    before_mesh = None
    apply_attempted = False
    operation_key = str(operation).lower()
    if operation_key not in _BOOLEAN_OPERATIONS:
        return skill_error("Invalid operation", "operation must be union, intersect, or subtract.")
    if input_a == input_b:
        return skill_error("Invalid operands", "Boolean operands must be distinct objects.")
    if output_name is not None and (
        not isinstance(output_name, str) or not output_name.strip() or len(output_name) > 255
    ):
        return skill_error("Invalid output_name", "output_name must contain between 1 and 255 characters.")
    try:
        import bpy

        left, error = mesh_object(bpy, input_a)
        if error:
            return error
        right, error = mesh_object(bpy, input_b)
        if error:
            return error
        if output_name:
            occupied = bpy.data.objects.get(output_name)
            if occupied is not None and object_identity(occupied) != object_identity(left):
                return skill_error(
                    f"Object already exists: {output_name}",
                    "Choose an output_name that is unowned or already belongs to input_a.",
                )
        if len(left.modifiers) >= 128:
            return skill_error("Modifier limit reached", "Refuse to add more than 128 modifiers to one object.")
        before_mesh = mesh_state(left)
        select_object(bpy, left)
        modifier = left.modifiers.new(name="Boolean_Operation", type="BOOLEAN")
        modifier.operation = _BOOLEAN_OPERATIONS[operation_key]
        modifier.object = right
        if hasattr(modifier, "solver"):
            modifier.solver = "EXACT"
        modifier_name = modifier.name
        configured = (
            object_identity(modifier.object) == object_identity(right)
            and str(modifier.operation) == _BOOLEAN_OPERATIONS[operation_key]
            and str(modifier.type) == "BOOLEAN"
        )
        if not configured:
            rollback_attempted = True
            try:
                left.modifiers.remove(modifier)
            except Exception:
                pass
            modifier_present = left.modifiers.get(modifier_name) is not None
            return skill_error(
                "Boolean configuration failed",
                "Blender did not retain the requested operands.",
                mutation_applied=modifier_present,
                rollback_attempted=rollback_attempted,
                rollback_verified=not modifier_present,
                modifier_name=modifier_name,
                modifier_present=modifier_present,
            )
        apply_finished = False
        if bool(apply):
            apply_attempted = True
            apply_finished = operator_finished(bpy.ops.object.modifier_apply(modifier=modifier_name))
        present = left.modifiers.get(modifier_name) is not None
        after_mesh, evidence_error = post_mutation_mesh_state("Boolean", left, before_mesh)
        if evidence_error:
            return evidence_error
        verified = (
            not present and apply_finished and after_mesh["mesh_digest"] != before_mesh["mesh_digest"]
            if bool(apply)
            else present
        )
        if not verified:
            context = {}
            if bool(apply):
                context = {
                    "mutation_applied": True,
                    "rollback_attempted": False,
                    "rollback_verified": False,
                    "mesh_before": before_mesh,
                    "mesh_after": after_mesh,
                }
            return skill_error(
                f"Boolean readback failed: {input_a}", "Modifier application or mesh state did not match.", **context
            )
        if output_name:
            left.name = output_name
            if getattr(left, "data", None) is not None:
                left.data.name = output_name
            actual_object_name = str(left.name)
            actual_mesh_name = str(getattr(getattr(left, "data", None), "name", ""))
            if actual_object_name != output_name or actual_mesh_name != output_name:
                return skill_error(
                    f"Boolean output rename failed: {input_a}",
                    "Blender did not retain the exact requested object and mesh names.",
                    mutation_applied=True,
                    rollback_attempted=False,
                    rollback_verified=False,
                    requested_output_name=output_name,
                    actual_object_name=actual_object_name,
                    actual_mesh_name=actual_mesh_name,
                    mesh_before=before_mesh,
                    mesh_after=after_mesh,
                )
        return skill_success(
            f"Applied {operation_key} Boolean to {left.name}",
            inputs=[input_a, input_b],
            parameters={"apply": bool(apply), "operation": operation_key, "output_name": output_name},
            readback={
                "applied": bool(apply),
                "modifier_present": present,
                "object_name": left.name,
                "operand": right.name,
                "operation": operation_key,
                "verified": True,
                "mesh_before": before_mesh,
                "mesh_after": after_mesh,
            },
            prompt="Use get_poly_count to inspect the Boolean result.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        if left is not None and modifier is not None:
            return _modifier_exception_receipt(bpy, left, modifier, before_mesh, apply_attempted, exc, "Boolean")
        return skill_exception(exc, message=f"Failed Boolean operation on {input_a}")


def delete_history(object_name: str) -> dict:
    """Apply a bounded Blender modifier stack and verify it is empty."""
    obj = None
    before_mesh = None
    before_modifiers = []
    applied = []
    current_name = None
    operation_started = False
    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        modifiers = list(obj.modifiers)
        if len(modifiers) > 128:
            return skill_error("Modifier limit exceeded", "Refuse to apply more than 128 modifiers in one call.")
        before_mesh = mesh_state(obj)
        before_modifiers = [str(modifier.name) for modifier in modifiers]
        select_object(bpy, obj)
        for modifier in modifiers:
            name = str(modifier.name)
            current_name = name
            operation_started = True
            finished = operator_finished(bpy.ops.object.modifier_apply(modifier=name))
            remaining = [str(current.name) for current in obj.modifiers]
            if not finished or name in remaining:
                after_counts = mesh_evidence_counts(obj)
                if after_counts["evidence_limited"]:
                    return skill_error(
                        f"History cleanup incomplete: {object_name}",
                        f"Modifier '{name}' left a mesh too large for bounded verification.",
                        mutation_applied=True,
                        rollback_attempted=False,
                        rollback_verified=False,
                        applied_modifiers=applied,
                        remaining_modifiers=remaining,
                        failed_modifier=name,
                        mesh_before=before_mesh,
                        mesh_after_counts=after_counts,
                    )
                after_mesh = mesh_state(obj)
                return skill_error(
                    f"History cleanup incomplete: {object_name}",
                    f"Modifier '{name}' was not applied.",
                    mutation_applied=(
                        remaining != before_modifiers or after_mesh["mesh_digest"] != before_mesh["mesh_digest"]
                    ),
                    rollback_attempted=False,
                    rollback_verified=False,
                    applied_modifiers=applied,
                    remaining_modifiers=remaining,
                    failed_modifier=name,
                    mesh_before=before_mesh,
                    mesh_after=after_mesh,
                )
            applied.append(name)
        remaining = [str(modifier.name) for modifier in obj.modifiers]
        if remaining:
            after_counts = mesh_evidence_counts(obj)
            if after_counts["evidence_limited"]:
                return skill_error(
                    f"History cleanup incomplete: {object_name}",
                    "The remaining mesh is too large for bounded verification.",
                    mutation_applied=True,
                    rollback_attempted=False,
                    rollback_verified=False,
                    applied_modifiers=applied,
                    remaining_modifiers=remaining,
                    mesh_before=before_mesh,
                    mesh_after_counts=after_counts,
                )
            after_mesh = mesh_state(obj)
            return skill_error(
                f"History cleanup incomplete: {object_name}",
                f"Remaining modifiers: {remaining}",
                mutation_applied=(
                    remaining != before_modifiers or after_mesh["mesh_digest"] != before_mesh["mesh_digest"]
                ),
                rollback_attempted=False,
                rollback_verified=False,
                applied_modifiers=applied,
                remaining_modifiers=remaining,
                mesh_before=before_mesh,
                mesh_after=after_mesh,
            )
        return skill_success(
            f"Applied {len(applied)} modifier(s) on {object_name}",
            object_name=obj.name,
            readback={"applied_modifiers": applied, "remaining_modifiers": remaining, "verified": True},
            prompt="Use get_poly_count and list_modifiers to inspect the result.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        if obj is not None and operation_started:
            try:
                remaining = [str(current.name) for current in obj.modifiers]
            except Exception:
                remaining = None
            observed_applied = (
                [name for name in before_modifiers if name not in remaining] if remaining is not None else list(applied)
            )
            try:
                after_counts = mesh_evidence_counts(obj)
            except Exception:
                after_counts = None
            return skill_error(
                f"History verification failed: {object_name}",
                "The modifier stack was partially evaluated before verification failed.",
                mutation_applied=True,
                rollback_attempted=False,
                rollback_verified=False,
                error_type=type(exc).__name__,
                applied_modifiers=observed_applied,
                remaining_modifiers=remaining,
                failed_modifier=current_name,
                mesh_before=before_mesh,
                mesh_after_counts=after_counts,
            )
        return skill_exception(exc, message=f"Failed to delete history for {object_name}")
