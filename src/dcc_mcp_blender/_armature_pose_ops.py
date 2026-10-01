"""Bounded armature inspection and validated pose channel updates.

The host API is imported only at the operation boundary. Pose updates use RNA
channels, so they do not depend on an editor, selection, or pose mode.
"""

from __future__ import annotations

import math
import struct
from itertools import islice
from numbers import Real
from typing import Any, Mapping, Sequence

from dcc_mcp_core.skills_helper import skill_error, skill_exception, skill_success

_EULER_MODES = {"XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"}
_CHANNELS = ("location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale")
_UPDATE_FIELDS = {"bone_name", "location", "rotation_euler", "rotation_quaternion", "rotation_mode", "scale"}
_MAX_UPDATES = 1024
_MAX_VALUE = 1_000_000.0


def _limit(value: int, label: str, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{label} must be an integer between 1 and {maximum}.")


def _names(value: Sequence[str] | None, label: str, maximum: int) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= maximum:
        raise ValueError(f"{label} must contain 1 to {maximum} distinct names.")
    if any(not isinstance(name, str) or not name.strip() for name in value) or len(set(value)) != len(value):
        raise ValueError(f"{label} must contain distinct non-empty strings.")
    return list(value)


def _coordinates(value: Any, label: str, size: int) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{label} must contain exactly {size} numbers.")
    if any(isinstance(item, bool) or not isinstance(item, Real) for item in value):
        raise ValueError(f"{label} must contain numbers, not booleans or strings.")
    result = [float(item) for item in value]
    if any(not math.isfinite(item) or abs(item) > _MAX_VALUE for item in result):
        raise ValueError(f"{label} must be finite and have absolute values at most {_MAX_VALUE:g}.")
    return result


def _armature(bpy: Any, name: str) -> Any:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("armature_name must be a non-empty string.")
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "ARMATURE":
        raise ValueError(f"Armature object not found: {name}.")
    if obj.mode == "EDIT":
        raise ValueError("Leave armature edit mode before inspecting or updating pose channels.")
    return obj


def _matrix(value: Any) -> list[list[float]]:
    result = [[float(component) for component in row] for row in value]
    if len(result) != 4 or any(len(row) != 4 or not all(math.isfinite(item) for item in row) for row in result):
        raise ValueError("Native matrix readback must be a finite 4 by 4 matrix.")
    return result


def _pose_channels(bone: Any) -> dict:
    channels = {name: [float(item) for item in getattr(bone, name)] for name in _CHANNELS}
    if any(not math.isfinite(item) for channel in channels.values() for item in channel):
        raise ValueError(f"Non-finite native pose channels on {bone.name}.")
    return {"rotation_mode": bone.rotation_mode, **channels}


def _pose_readback(bone: Any, evaluated_bone: Any) -> dict:
    return {
        **_pose_channels(bone),
        "matrix_basis": _matrix(bone.matrix_basis),
        "matrix_armature_space": _matrix(evaluated_bone.matrix),
    }


def _evaluated_bones(bpy: Any, armature: Any) -> Any:
    bpy.context.view_layer.update()
    return armature.evaluated_get(bpy.context.evaluated_depsgraph_get()).pose.bones


def _constraint_summary(bone: Any, limit: int) -> dict:
    items = []
    for constraint in islice(bone.constraints, limit):
        items.append(
            {
                "name": constraint.name,
                "type": constraint.type,
                "influence": float(constraint.influence),
                "mute": bool(constraint.mute),
                "target": getattr(getattr(constraint, "target", None), "name", None),
                "subtarget": getattr(constraint, "subtarget", None),
                "owner_space": getattr(constraint, "owner_space", None),
                "target_space": getattr(constraint, "target_space", None),
            }
        )
    return {"items": items, "total_count": len(bone.constraints), "truncated": len(bone.constraints) > limit}


def _mesh_weights(mesh: Any, rest_bones: Any, max_vertices: int) -> dict:
    groups = {
        group.index: group.name
        for group in mesh.vertex_groups
        if rest_bones.get(group.name) is not None and rest_bones[group.name].use_deform
    }
    count = min(len(mesh.data.vertices), max_vertices)
    weighted = 0
    assignments = 0
    invalid = 0
    maximum_influences = 0
    sums = []
    for vertex in mesh.data.vertices[:count]:
        weights = []
        for membership in vertex.groups:
            if membership.group not in groups:
                continue
            weight = float(membership.weight)
            if not math.isfinite(weight) or weight < 0 or weight > 1:
                invalid += 1
            elif weight > 0:
                weights.append(weight)
        weighted += bool(weights)
        assignments += len(weights)
        maximum_influences = max(maximum_influences, len(weights))
        sums.append(sum(weights))
    return {
        "mesh_name": mesh.name,
        "vertex_count": len(mesh.data.vertices),
        "scanned_vertex_count": count,
        "scan_complete": count == len(mesh.data.vertices),
        "sampling": "vertex_index_prefix",
        "matched_bone_group_count": len(groups),
        "weighted_scanned_vertices": weighted,
        "unweighted_scanned_vertices": count - weighted,
        "positive_assignment_count": assignments,
        "invalid_assignment_count": invalid,
        "maximum_influences": maximum_influences,
        "weight_sum_min": min(sums) if sums else None,
        "weight_sum_max": max(sums) if sums else None,
    }


def inspect_armature(
    armature_name: str,
    bone_names: Sequence[str] | None = None,
    max_bones: int = 256,
    include_constraints: bool = True,
    max_constraints_per_bone: int = 32,
    mesh_names: Sequence[str] | None = None,
    max_vertices_per_mesh: int = 10000,
) -> dict:
    """Read bounded rest/pose data and optional explicitly selected skin summaries."""
    try:
        _limit(max_bones, "max_bones", _MAX_UPDATES)
        _limit(max_constraints_per_bone, "max_constraints_per_bone", 128)
        _limit(max_vertices_per_mesh, "max_vertices_per_mesh", 100000)
        names = _names(bone_names, "bone_names", max_bones)
        meshes = _names(mesh_names, "mesh_names", 16) or []
        if not isinstance(include_constraints, bool):
            raise ValueError("include_constraints must be boolean.")
        import bpy

        armature = _armature(bpy, armature_name)
        rest = armature.data.bones
        names = names if names is not None else [bone.name for bone in rest[:max_bones]]
        if any(rest.get(name) is None or armature.pose.bones.get(name) is None for name in names):
            raise ValueError("Every requested bone must have both rest and pose data.")
        selected_meshes = []
        for name in meshes:
            mesh = bpy.data.objects.get(name)
            if mesh is None or mesh.type != "MESH" or mesh.mode == "EDIT":
                raise ValueError(f"Mesh object unavailable in object/pose mode: {name}.")
            if not any(mod.type == "ARMATURE" and mod.object == armature for mod in mesh.modifiers):
                raise ValueError(f"Mesh {name} has no Armature modifier targeting {armature_name}.")
            selected_meshes.append(mesh)
        evaluated = _evaluated_bones(bpy, armature)
        bones = []
        for name in names:
            bone = rest[name]
            pose = armature.pose.bones[name]
            item = {
                "bone_name": name,
                "parent": bone.parent.name if bone.parent else None,
                "connected": bool(bone.use_connect),
                "use_deform": bool(bone.use_deform),
                "rest": {
                    "head_armature_space": list(bone.head_local),
                    "tail_armature_space": list(bone.tail_local),
                    "matrix_armature_space": _matrix(bone.matrix_local),
                    "length": float(bone.length),
                },
                "pose": _pose_readback(pose, evaluated[name]),
            }
            if include_constraints:
                item["constraints"] = _constraint_summary(pose, max_constraints_per_bone)
            bones.append(item)
        return skill_success(
            f"Inspected {len(bones)} bone(s) on {armature.name}",
            schema="blender.armature-inspection.v1",
            armature_name=armature.name,
            armature_matrix_world=_matrix(armature.matrix_world),
            frame=int(bpy.context.scene.frame_current),
            bone_count=len(rest),
            returned_bone_count=len(bones),
            truncated=len(bones) < len(rest),
            bones=bones,
            mesh_weight_summaries=[_mesh_weights(mesh, rest, max_vertices_per_mesh) for mesh in selected_meshes],
            prompt="Use set_pose_bone_transforms for local channels; inspect sampled skin coverage before relying on it.",
        )
    except ValueError as exc:
        return skill_error("Invalid armature inspection", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to inspect armature {armature_name}")


def _validated_updates(armature: Any, transforms: Any) -> list[tuple[Any, dict]]:
    if not isinstance(transforms, (list, tuple)) or not 1 <= len(transforms) <= _MAX_UPDATES:
        raise ValueError(f"transforms must contain 1 to {_MAX_UPDATES} bone updates.")
    validated = []
    names = set()
    for spec in transforms:
        if not isinstance(spec, Mapping) or set(spec) - _UPDATE_FIELDS:
            raise ValueError("Each transform must be an object containing only documented fields.")
        name = spec.get("bone_name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Each transform must name a distinct, non-empty bone.")
        bone = armature.pose.bones.get(name)
        if bone is None:
            raise ValueError(f"Pose bone not found: {name}.")
        names.add(name)
        values = {}
        for field, size in (("location", 3), ("scale", 3), ("rotation_euler", 3), ("rotation_quaternion", 4)):
            if field in spec:
                values[field] = _coordinates(spec[field], f"{name}.{field}", size)
        if not values:
            raise ValueError(f"{name}: supply at least one transform channel.")
        if "scale" in values and any(abs(component) < 1e-6 for component in values["scale"]):
            raise ValueError(f"{name}: scale components must have absolute values at least 1e-6.")
        if "rotation_euler" in values and "rotation_quaternion" in values:
            raise ValueError(f"{name}: Euler and quaternion rotations are mutually exclusive.")
        if "rotation_quaternion" in values:
            if any(abs(component) > 1 for component in values["rotation_quaternion"]):
                raise ValueError(f"{name}: quaternion components must lie between -1 and 1.")
            if spec.get("rotation_mode", "QUATERNION") != "QUATERNION":
                raise ValueError(f"{name}: quaternion rotations require QUATERNION mode.")
            if not math.isclose(sum(item * item for item in values["rotation_quaternion"]), 1.0, abs_tol=1e-6):
                raise ValueError(f"{name}: rotation_quaternion must be a unit quaternion in w,x,y,z order.")
            values["rotation_mode"] = "QUATERNION"
        elif "rotation_euler" in values:
            mode = spec.get("rotation_mode", "XYZ")
            if not isinstance(mode, str) or mode not in _EULER_MODES:
                raise ValueError(f"{name}: rotation_euler requires a supported Euler order.")
            values["rotation_mode"] = mode
        elif "rotation_mode" in spec:
            raise ValueError(f"{name}: rotation_mode requires an explicit rotation channel.")
        if any(bone.is_property_readonly(field) for field in values):
            raise ValueError(f"{name}: a requested RNA channel is read-only.")
        validated.append((bone, values))
    return validated


def _apply_channels(bone: Any, values: dict) -> None:
    if "rotation_mode" in values:
        bone.rotation_mode = values["rotation_mode"]
    for field, value in values.items():
        if field != "rotation_mode":
            setattr(bone, field, value)


def _matches(bone: Any, values: dict) -> bool:
    for field, requested in values.items():
        actual = getattr(bone, field)
        if field == "rotation_mode":
            if actual != requested:
                return False
        elif len(actual) != len(requested) or not all(
            float(a) in (b, struct.unpack("f", struct.pack("f", b))[0]) for a, b in zip(actual, requested)
        ):
            return False
    return True


def set_pose_bone_transforms(armature_name: str, transforms: Sequence[Mapping[str, Any]]) -> dict:
    """Set a validated batch of rest-relative local pose channels without keyframes."""
    try:
        import bpy

        armature = _armature(bpy, armature_name)
        updates = _validated_updates(armature, transforms)
        snapshots = [(bone, _pose_channels(bone)) for bone, _ in updates]
        try:
            for bone, values in updates:
                _apply_channels(bone, values)
            evaluated = _evaluated_bones(bpy, armature)
            if any(not _matches(bone, values) for bone, values in updates):
                raise RuntimeError(
                    "Pose channel readback differs from the requested values after dependency evaluation."
                )
            result = [
                {"bone_name": bone.name, "requested": values, "readback": _pose_readback(bone, evaluated[bone.name])}
                for bone, values in updates
            ]
        except Exception as exc:
            rollback_errors = []
            for bone, snapshot in snapshots:
                try:
                    _apply_channels(bone, snapshot)
                except Exception as rollback_exc:
                    rollback_errors.append(f"{bone.name}: {rollback_exc}")
            try:
                _evaluated_bones(bpy, armature)
                if any(not _matches(bone, snapshot) for bone, snapshot in snapshots):
                    rollback_errors.append("Restored channel readback differs from the original values.")
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
            return skill_error(
                "Pose update failed",
                str(exc),
                rolled_back=not rollback_errors,
                rollback_errors=rollback_errors,
                prompt="Inspect the rig and its drivers before retrying; rollback failure requires scene recovery.",
            )
        return skill_success(
            f"Updated {len(result)} pose bone(s) on {armature.name}",
            schema="blender.pose-channel-update.v1",
            armature_name=armature.name,
            frame=int(bpy.context.scene.frame_current),
            transform_space="rest_relative_local_channels",
            quaternion_order="wxyz",
            updated_bone_count=len(result),
            transforms=result,
            prompt="Inspect evaluated matrices for constraints; use blender-animation to insert keyframes separately.",
        )
    except ValueError as exc:
        return skill_error("Invalid pose transforms", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update pose channels on {armature_name}")
