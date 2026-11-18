"""Read-only validation for the complete photographic toy-shot contract."""

from __future__ import annotations

import math
from typing import Any, Iterable

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._animation_ops import action_fcurves
from dcc_mcp_blender._photographic_lighting_ops import validate_motivated_lighting
from dcc_mcp_blender._photographic_post_ops import validate_photographic_post
from dcc_mcp_blender._render_profile_ops import validate_render_profile


def _resolve_scene(bpy: Any, scene_name: str | None) -> tuple[Any | None, dict | None]:
    if scene_name:
        scene = bpy.data.scenes.get(str(scene_name))
        if scene is None:
            return None, skill_error(f"Scene not found: {scene_name}", f"No scene named '{scene_name}'.")
        return scene, None
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return None, skill_error("No active scene", "bpy.context.scene is unavailable.")
    return scene, None


def _object(bpy: Any, name: str | None) -> Any | None:
    return bpy.data.objects.get(name) if name else None


def _keyframe_frame(point: Any) -> float | None:
    co = getattr(point, "co", None)
    if co is None:
        return None
    return float(co.x if hasattr(co, "x") else co[0])


def _keyframe_value(point: Any) -> float | None:
    co = getattr(point, "co", None)
    if co is None:
        return None
    return float(co.y if hasattr(co, "y") else co[1])


def _iter_materials(obj: Any) -> Iterable[Any]:
    slots = getattr(obj, "material_slots", None)
    if slots:
        for slot in slots:
            material = getattr(slot, "material", None)
            if material is not None:
                yield material
        return
    materials = getattr(getattr(obj, "data", None), "materials", None)
    for material in materials or ():
        if material is not None:
            yield material


def _has_node_material(obj: Any) -> bool:
    return any(getattr(material, "use_nodes", False) and getattr(material, "node_tree", None) for material in _iter_materials(obj))


def _has_texture_material(obj: Any) -> bool:
    for material in _iter_materials(obj):
        tree = getattr(material, "node_tree", None)
        for node in getattr(tree, "nodes", ()) if tree is not None else ():
            node_type = str(getattr(node, "bl_idname", ""))
            if node_type in {"ShaderNodeTexImage", "ShaderNodeTexEnvironment"}:
                return True
    return False


def _issue(issues: list[dict], code: str, field: str, message: str, severity: str = "error", **details: Any) -> None:
    item = {"code": code, "field": field, "message": message, "severity": severity}
    if details:
        item["details"] = details
    issues.append(item)


def _validate_camera(
    scene: Any,
    camera: Any,
    focus_object: Any | None,
    shot_type: str,
    floor_z: float,
    frame_range: tuple[int, int],
    issues: list[dict],
) -> dict[str, Any]:
    data = getattr(camera, "data", None)
    dof = getattr(data, "dof", None)
    location = getattr(camera, "location", (0.0, 0.0, 0.0))
    height = float(getattr(location, "z", location[2])) - floor_z
    state = {
        "name": getattr(camera, "name", None),
        "lens": getattr(data, "lens", None),
        "sensor_width": getattr(data, "sensor_width", None),
        "height_m": height,
        "dof_enabled": getattr(dof, "use_dof", None),
        "aperture_fstop": getattr(dof, "aperture_fstop", None),
        "aperture_blades": getattr(dof, "aperture_blades", None),
        "focus_object": getattr(getattr(dof, "focus_object", None), "name", None),
    }
    if getattr(camera, "type", None) != "CAMERA":
        _issue(issues, "PHOTO_CAMERA_TYPE", "camera", "The target object is not a camera.")
        return state
    if state["sensor_width"] is None or not math.isclose(float(state["sensor_width"]), 36.0, abs_tol=1e-6):
        _issue(issues, "PHOTO_CAMERA_SENSOR", "sensor_width", "Camera sensor width must be 36 mm.", expected=36.0, actual=state["sensor_width"])
    if state["lens"] is None or not 24.0 <= float(state["lens"]) <= 85.0:
        _issue(issues, "PHOTO_CAMERA_LENS", "lens", "Camera lens must be between 24 and 85 mm.", expected=[24.0, 85.0], actual=state["lens"])
    if state["height_m"] < 0.01 or state["height_m"] > 0.08:
        _issue(issues, "PHOTO_CAMERA_HEIGHT", "location.z", "Camera height must be 1 to 8 cm above the floor.", expected=[0.01, 0.08], actual=state["height_m"])
    if state["dof_enabled"] is not True:
        _issue(issues, "PHOTO_CAMERA_DOF", "dof.use_dof", "Depth of field must be enabled.")
    expected_fstop = 11.0 if shot_type == "WIDE" else None
    if expected_fstop is not None:
        if not math.isclose(float(state["aperture_fstop"] or 0.0), expected_fstop, abs_tol=1e-6):
            _issue(issues, "PHOTO_CAMERA_FSTOP", "aperture_fstop", "Wide establishing shots require f/11.", expected=11.0, actual=state["aperture_fstop"])
    elif state["aperture_fstop"] is None or not 2.8 <= float(state["aperture_fstop"]) <= 5.6:
        _issue(issues, "PHOTO_CAMERA_FSTOP", "aperture_fstop", "Character shots require f/2.8 to f/5.6.", expected=[2.8, 5.6], actual=state["aperture_fstop"])
    if state["aperture_blades"] not in (None, 0):
        _issue(issues, "PHOTO_CAMERA_APERTURE", "aperture_blades", "The photographic camera must use a round aperture.", expected=0, actual=state["aperture_blades"])
    focus_target = getattr(dof, "focus_object", None)
    if focus_target is None:
        _issue(issues, "PHOTO_CAMERA_FOCUS_MISSING", "focus_object", "Depth of field must focus on the character's eyes.")
    elif focus_object is not None and focus_target is not focus_object:
        _issue(
            issues,
            "PHOTO_CAMERA_FOCUS",
            "focus_object",
            "Depth of field must focus on the requested eye focus object.",
            expected=getattr(focus_object, "name", None),
            actual=state["focus_object"],
        )

    curves = []
    for _, curve in action_fcurves(camera):
        if getattr(curve, "data_path", None) in {"location", "rotation_euler"}:
            curves.append(curve)
    if not curves:
        _issue(issues, "PHOTO_CAMERA_ANIMATION_MISSING", "animation", "Every shot requires an eased camera move.")
        return state
    first_frames = [_keyframe_frame(point) for curve in curves for point in getattr(curve, "keyframe_points", ())]
    frames = [frame for frame in first_frames if frame is not None]
    if not frames:
        _issue(issues, "PHOTO_CAMERA_KEYS_MISSING", "animation", "Camera animation curves contain no readable keyframes.")
        return state
    start, end = frame_range
    if min(frames) > start - 1 or max(frames) < end + 1:
        _issue(
            issues,
            "PHOTO_CAMERA_ENDPOINT_EXTENSION",
            "animation",
            "Camera animation must extend one frame past both shot endpoints.",
            expected=[start - 1, end + 1],
            actual=[min(frames), max(frames)],
        )
    if not any(getattr(point, "interpolation", None) == "BEZIER" for curve in curves for point in getattr(curve, "keyframe_points", ())):
        _issue(issues, "PHOTO_CAMERA_EASING", "animation", "Camera moves must contain at least one Bezier keyframe.", severity="warning")
    for curve in curves:
        if getattr(curve, "data_path", None) != "rotation_euler":
            continue
        points = list(getattr(curve, "keyframe_points", ()))
        values = [_keyframe_value(point) for point in points]
        values = [value for value in values if value is not None]
        if any(abs(second - first) > math.pi for first, second in zip(values, values[1:])):
            _issue(issues, "PHOTO_CAMERA_ROTATION_DISCONTINUITY", "rotation_euler", "Camera Euler rotation jumps more than 180 degrees between keys.")
    return state


def _validate_surface(obj: Any | None, role: str, issues: list[dict]) -> dict[str, Any]:
    state = {"name": getattr(obj, "name", None), "type": getattr(obj, "type", None) if obj else None}
    if obj is None:
        _issue(issues, "PHOTO_SURFACE_MISSING", role, f"The {role} object was not found.")
        return state
    if getattr(obj, "type", None) != "MESH":
        _issue(issues, "PHOTO_SURFACE_TYPE", role, f"The {role} must be a mesh object.", actual=getattr(obj, "type", None))
        return state
    state["has_node_material"] = _has_node_material(obj)
    state["has_texture_material"] = _has_texture_material(obj)
    if not state["has_node_material"]:
        _issue(issues, "PHOTO_SURFACE_MATERIAL", role, f"The {role} needs a node-based material.")
    if not state["has_texture_material"]:
        _issue(issues, "PHOTO_SURFACE_TEXTURE", role, f"The {role} must use a textured or scanned surface material.")
    return state


def validate_photographic_shot(
    scene_name: str | None = None,
    camera_name: str | None = None,
    hero_object: str | None = None,
    focus_object: str | None = None,
    background_object: str | None = None,
    floor_object: str | None = None,
    wall_object: str | None = None,
    source_name: str | None = None,
    source_type: str = "LAMP",
    shot_type: str = "CHARACTER",
    floor_z: float = 0.0,
    frame_range: list[int] | tuple[int, int] | None = None,
    profile_name: str = "FINAL",
    require_post: bool = True,
) -> dict:
    """Run machine-readable checks for the prompt's complete shot contract."""
    try:
        shot = str(shot_type or "CHARACTER").strip().upper()
        if shot not in {"CHARACTER", "WIDE"}:
            raise ValueError("shot_type must be CHARACTER or WIDE")
        profile = str(profile_name or "FINAL").strip().upper()
        if profile not in {"PREVIEW", "FINAL"}:
            raise ValueError("profile_name must be PREVIEW or FINAL")
        if frame_range is None:
            requested_range = None
        elif isinstance(frame_range, (str, bytes)) or len(frame_range) != 2:
            raise ValueError("frame_range must contain [start, end]")
        else:
            requested_range = (int(frame_range[0]), int(frame_range[1]))
            if requested_range[0] > requested_range[1]:
                raise ValueError("frame_range start must be less than or equal to end")
        if not isinstance(floor_z, (int, float)) or isinstance(floor_z, bool) or not math.isfinite(float(floor_z)):
            raise ValueError("floor_z must be a finite number")

        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        issues: list[dict] = []
        camera = _object(bpy, camera_name) if camera_name else getattr(scene, "camera", None)
        hero = _object(bpy, hero_object)
        focus = _object(bpy, focus_object)
        background = _object(bpy, background_object)
        floor = _object(bpy, floor_object)
        wall = _object(bpy, wall_object)
        active_range = requested_range or (int(getattr(scene, "frame_start", 1)), int(getattr(scene, "frame_end", 1)))

        unit_settings = getattr(scene, "unit_settings", None)
        units = {
            "system": getattr(unit_settings, "system", None),
            "scale_length": getattr(unit_settings, "scale_length", None),
            "length_unit": getattr(unit_settings, "length_unit", None),
        }
        if units["system"] != "METRIC" or units["scale_length"] is None or not math.isclose(float(units["scale_length"]), 1.0, abs_tol=1e-6):
            _issue(issues, "PHOTO_SCENE_UNITS", "unit_settings", "The scene must use metres at unit scale 1.0.", expected={"system": "METRIC", "scale_length": 1.0}, actual=units)

        camera_state = (
            _validate_camera(scene, camera, focus, shot, float(floor_z), active_range, issues)
            if camera
            else None
        )
        if camera is None:
            _issue(issues, "PHOTO_CAMERA_MISSING", "camera", "The scene has no active camera.")
        if focus_object and focus is None:
            _issue(
                issues,
                "PHOTO_FOCUS_OBJECT_MISSING",
                "focus_object",
                "The requested eye focus object was not found.",
            )

        hero_state = {"name": getattr(hero, "name", None)}
        if hero is not None:
            if getattr(hero, "type", None) != "MESH":
                _issue(issues, "PHOTO_HERO_TYPE", "hero_object", "The hero must be a mesh object.")
            dimensions = getattr(hero, "dimensions", None)
            maximum_dimension = max(float(value) for value in dimensions) if dimensions else None
            hero_state["maximum_dimension_m"] = maximum_dimension
            if maximum_dimension is not None and not 0.025 <= maximum_dimension <= 0.067:
                _issue(issues, "PHOTO_HERO_SCALE", "hero_object", "The hero must be 25 to 67 mm tall or wide.", expected=[0.025, 0.067], actual=maximum_dimension)
            if not _has_node_material(hero):
                _issue(issues, "PHOTO_HERO_MATERIAL", "hero_object", "The hero needs a node-based material.")
            bevels = [modifier for modifier in getattr(hero, "modifiers", ()) if getattr(modifier, "type", None) == "BEVEL"]
            hero_state["bevels"] = [{"width": getattr(modifier, "width", None), "segments": getattr(modifier, "segments", None)} for modifier in bevels]
            if not any(0.0003 <= float(getattr(modifier, "width", 0.0)) <= 0.0007 and int(getattr(modifier, "segments", 0)) == 3 for modifier in bevels):
                _issue(issues, "PHOTO_HERO_BEVEL", "hero_object", "Every hero edge needs a 0.3 to 0.7 mm, 3-segment bevel.")

        surfaces = {}
        if floor_object:
            surfaces["floor"] = _validate_surface(floor, "floor", issues)
        if wall_object:
            surfaces["wall"] = _validate_surface(wall, "wall", issues)
        if background_object and background is None:
            _issue(issues, "PHOTO_BACKGROUND_MISSING", "background_object", "The background object was not found.")

        hidden_animation = []
        for obj in getattr(bpy.data, "objects", ()):
            for _, curve in action_fcurves(obj):
                if getattr(curve, "data_path", None) == "hide_render":
                    hidden_animation.append(getattr(obj, "name", None))
        if hidden_animation:
            _issue(issues, "PHOTO_HIDE_RENDER_ANIMATED", "hide_render", "Shot switching must not animate object.hide_render.", objects=hidden_animation)

        profile_report = validate_render_profile(profile_name=profile, scene_name=getattr(scene, "name", scene_name))
        if not profile_report.get("success") or profile_report.get("context", {}).get("valid") is False:
            _issue(issues, "PHOTO_RENDER_PROFILE", "render_profile", "The selected photographic render profile is invalid.", details=profile_report.get("context", {}))
        post_report = None
        if require_post:
            post_report = validate_photographic_post(scene_name=getattr(scene, "name", scene_name))
            if not post_report.get("success") or post_report.get("context", {}).get("valid") is False:
                _issue(issues, "PHOTO_POST_STACK", "post", "The photographic compositor finish is invalid.", details=post_report.get("context", {}))
        lighting_report = None
        if source_name:
            lighting_report = validate_motivated_lighting(
                source_name=source_name,
                source_type=source_type,
                hero_object=hero_object,
                background_object=background_object,
            )
            lighting_context = lighting_report.get("context", {})
            if not lighting_report.get("success") or lighting_context.get("valid") is False:
                _issue(issues, "PHOTO_LIGHTING_CONTRACT", "lighting", "The motivated lighting contract is invalid.", details=lighting_context)

        return skill_success(
            "Photographic shot validation completed",
            valid=not issues,
            issues=issues,
            scene_name=getattr(scene, "name", scene_name),
            frame_range=list(active_range),
            shot_type=shot,
            profile_name=profile,
            units=units,
            camera=camera_state,
            focus_object=getattr(focus, "name", focus_object),
            hero=hero_state,
            surfaces=surfaces,
            hidden_render_animation=hidden_animation,
            render_profile=profile_report.get("context", profile_report),
            photographic_post=post_report.get("context", post_report) if post_report else None,
            motivated_lighting=lighting_report.get("context", lighting_report) if lighting_report else None,
        )
    except ValueError as exc:
        return skill_error("Invalid photographic shot request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate photographic shot")
