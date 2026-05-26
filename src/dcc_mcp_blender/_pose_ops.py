"""Shared implementations for Blender pose library operation tools."""

from __future__ import annotations

import json
from typing import Any

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_POSE_STORE_KEY = "dcc_mcp_poses"


def _object_by_name(bpy: Any, object_name: str) -> tuple[Any | None, dict | None]:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    return obj, None


def _armature(bpy: Any, armature_name: str) -> tuple[Any | None, dict | None]:
    obj, error = _object_by_name(bpy, armature_name)
    if error:
        return None, error
    if getattr(obj, "type", None) != "ARMATURE":
        return None, skill_error(f"{armature_name} is not an armature", f"Object type is {getattr(obj, 'type', None)}.")
    return obj, None


def _pose_bones(armature: Any) -> dict[str, Any]:
    pose = getattr(armature, "pose", None)
    bones = getattr(pose, "bones", []) if pose is not None else []
    return {bone.name: bone for bone in bones}


def _as_list(value: Any, fallback: list[float]) -> list[float]:
    try:
        return [float(item) for item in value]
    except Exception:
        return list(fallback)


def _capture_bone(bone: Any) -> dict[str, Any]:
    return {
        "location": _as_list(getattr(bone, "location", []), [0.0, 0.0, 0.0]),
        "rotation_mode": getattr(bone, "rotation_mode", "XYZ"),
        "rotation_euler": _as_list(getattr(bone, "rotation_euler", []), [0.0, 0.0, 0.0]),
        "rotation_quaternion": _as_list(getattr(bone, "rotation_quaternion", []), [1.0, 0.0, 0.0, 0.0]),
        "scale": _as_list(getattr(bone, "scale", []), [1.0, 1.0, 1.0]),
    }


def _apply_bone(bone: Any, values: dict[str, Any]) -> None:
    if "rotation_mode" in values and hasattr(bone, "rotation_mode"):
        bone.rotation_mode = values["rotation_mode"]
    for attr in ("location", "rotation_euler", "rotation_quaternion", "scale"):
        if attr in values and hasattr(bone, attr):
            setattr(bone, attr, values[attr])


def _get_custom_property(obj: Any, key: str, default: Any = None) -> Any:
    get = getattr(obj, "get", None)
    if callable(get):
        return get(key, default)
    try:
        return obj[key]
    except Exception:
        return default


def _set_custom_property(obj: Any, key: str, value: Any) -> None:
    try:
        obj[key] = value
    except Exception:
        setattr(obj, key, value)


def _load_store(armature: Any) -> dict[str, Any]:
    raw = _get_custom_property(armature, _POSE_STORE_KEY, "{}")
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_store(armature: Any, store: dict[str, Any]) -> None:
    _set_custom_property(armature, _POSE_STORE_KEY, json.dumps(store, sort_keys=True))


def _mirror_name(name: str) -> str:
    pairs = [
        (".L", ".R"),
        ("_L", "_R"),
        ("-L", "-R"),
        ("Left", "Right"),
        ("left", "right"),
        ("L_", "R_"),
    ]
    for left, right in pairs:
        if name.endswith(left):
            return name[: -len(left)] + right
        if name.endswith(right):
            return name[: -len(right)] + left
        if name.startswith(left):
            return right + name[len(left) :]
        if name.startswith(right):
            return left + name[len(right) :]
    return name


def _mirrored_values(values: dict[str, Any]) -> dict[str, Any]:
    mirrored = json.loads(json.dumps(values))
    if "location" in mirrored and len(mirrored["location"]) >= 1:
        mirrored["location"][0] = -float(mirrored["location"][0])
    if "rotation_euler" in mirrored and len(mirrored["rotation_euler"]) >= 3:
        mirrored["rotation_euler"][1] = -float(mirrored["rotation_euler"][1])
        mirrored["rotation_euler"][2] = -float(mirrored["rotation_euler"][2])
    return mirrored


def list_poses(armature_name: str | None = None) -> dict:
    """List saved poses stored on armatures."""
    try:
        import bpy

        armatures = []
        if armature_name:
            armature, error = _armature(bpy, armature_name)
            if error:
                return error
            armatures = [armature]
        else:
            armatures = [obj for obj in bpy.data.objects if getattr(obj, "type", None) == "ARMATURE"]
        poses = []
        for armature in armatures:
            store = _load_store(armature)
            for pose_name, pose_data in sorted(store.items()):
                poses.append(
                    {
                        "armature_name": armature.name,
                        "pose_name": pose_name,
                        "bone_count": len(pose_data.get("bones", {})),
                    }
                )
        return skill_success(
            f"Found {len(poses)} pose(s)",
            armature_name=armature_name,
            poses=poses,
            count=len(poses),
            prompt="Use load_pose to apply a saved pose or save_pose to capture the current pose.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list poses")


def save_pose(armature_name: str, pose_name: str) -> dict:
    """Save current pose-bone transforms to an armature-local pose store."""
    if not pose_name or not pose_name.strip():
        return skill_error("Invalid pose_name", "pose_name must be a non-empty string.")
    try:
        import bpy

        armature, error = _armature(bpy, armature_name)
        if error:
            return error
        bones = _pose_bones(armature)
        if not bones:
            return skill_error("No pose bones", f"{armature_name} has no pose bones to save.")
        store = _load_store(armature)
        store[pose_name] = {
            "armature_name": armature.name,
            "pose_name": pose_name,
            "bones": {name: _capture_bone(bone) for name, bone in bones.items()},
        }
        _save_store(armature, store)
        return skill_success(
            f"Saved pose {pose_name}",
            armature_name=armature.name,
            pose_name=pose_name,
            bone_count=len(bones),
            pose_count=len(store),
            prompt="Use list_poses to discover saved poses or load_pose to apply this pose.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to save pose {pose_name}")


def load_pose(armature_name: str, pose_name: str, mirror: bool = False) -> dict:
    """Load a saved armature pose."""
    try:
        import bpy

        armature, error = _armature(bpy, armature_name)
        if error:
            return error
        store = _load_store(armature)
        pose_data = store.get(pose_name)
        if pose_data is None:
            return skill_error(
                f"Pose not found: {pose_name}", f"{armature_name} has no saved pose named '{pose_name}'."
            )
        bones = _pose_bones(armature)
        applied = []
        missing = []
        for source_name, values in pose_data.get("bones", {}).items():
            target_name = _mirror_name(source_name) if mirror else source_name
            bone = bones.get(target_name)
            if bone is None:
                missing.append(target_name)
                continue
            _apply_bone(bone, _mirrored_values(values) if mirror else values)
            applied.append(target_name)
        return skill_success(
            f"Loaded pose {pose_name}",
            armature_name=armature.name,
            pose_name=pose_name,
            mirror=bool(mirror),
            applied_bones=applied,
            missing_bones=missing,
            applied_count=len(applied),
            prompt="Use save_pose to capture edits or bake_animation to bake pose changes.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to load pose {pose_name}")
