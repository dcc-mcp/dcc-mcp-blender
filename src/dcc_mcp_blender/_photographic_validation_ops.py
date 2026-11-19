"""Read-only validation for the complete photographic toy-shot contract."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._animation_ops import action_fcurves
from dcc_mcp_blender._photographic_lighting_ops import validate_motivated_lighting
from dcc_mcp_blender._photographic_material_ops import (
    NORMAL_MAP_CONVENTION,
    NORMAL_MAP_CONVENTION_KEY,
    PBR_MAPS,
    TEXTURE_SOURCE_KEY,
    _pbr_link_state,
    _pbr_texture_nodes,
    _uses_object_coordinates,
)
from dcc_mcp_blender._photographic_post_ops import validate_photographic_post
from dcc_mcp_blender._render_profile_ops import validate_render_profile

PHOTOGRAPHIC_GPU_BACKENDS = {"OPTIX", "METAL"}


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
    return any(
        getattr(material, "use_nodes", False) and getattr(material, "node_tree", None)
        for material in _iter_materials(obj)
    )


def _has_texture_material(obj: Any) -> bool:
    for material in _iter_materials(obj):
        tree = getattr(material, "node_tree", None)
        for node in getattr(tree, "nodes", ()) if tree is not None else ():
            node_type = str(getattr(node, "bl_idname", ""))
            if node_type in {"ShaderNodeTexImage", "ShaderNodeTexEnvironment"}:
                return True
    return False


def _custom_value(owner: Any, key: str, default: Any = None) -> Any:
    getter = getattr(owner, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except (TypeError, ValueError, RuntimeError):
            pass
    return getattr(owner, key, default)


def _preview_metadata_path(image_path: str) -> Path:
    return Path(f"{Path(image_path).expanduser().resolve()}.photographic.json")


def _read_preview_metadata(metadata_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_polyhaven_source(value: Any) -> bool:
    normalized = "".join(str(value or "").casefold().split())
    return normalized == "polyhaven" or "polyhaven.com" in normalized


def _pbr_surface_state(obj: Any | None) -> dict[str, Any]:
    materials = list(_iter_materials(obj)) if obj is not None else []
    material_states = []
    for material in materials:
        tree = getattr(material, "node_tree", None)
        nodes = _pbr_texture_nodes(tree) if tree is not None else {map_name: None for map_name in PBR_MAPS}
        map_states = {}
        for map_name, node in nodes.items():
            map_states[map_name] = {
                "present": node is not None,
                "image_loaded": node is not None and getattr(node, "image", None) is not None,
                "projection": getattr(node, "projection", None) if node is not None else None,
                "projection_blend": getattr(node, "projection_blend", None) if node is not None else None,
                "object_coordinates": _uses_object_coordinates(node) if node is not None else False,
            }
        source = _custom_value(material, TEXTURE_SOURCE_KEY)
        normal_map_convention = _custom_value(material, NORMAL_MAP_CONVENTION_KEY)
        links = _pbr_link_state(tree)
        material_states.append(
            {
                "name": getattr(material, "name", None),
                "texture_source": source,
                "polyhaven_source": _is_polyhaven_source(source),
                "normal_map_convention": normal_map_convention,
                "normal_map_convention_valid": normal_map_convention == NORMAL_MAP_CONVENTION,
                "links": links,
                "maps": map_states,
            }
        )

    valid_materials = []
    for state in material_states:
        maps_valid = all(
            details["present"]
            and details["image_loaded"]
            and details["projection"] == "BOX"
            and isinstance(details["projection_blend"], (int, float))
            and math.isclose(float(details["projection_blend"]), 0.25, abs_tol=1e-6)
            and details["object_coordinates"]
            for details in state["maps"].values()
        )
        valid_materials.append(
            maps_valid
            and state["polyhaven_source"]
            and state["normal_map_convention_valid"]
            and all(state["links"].values())
        )
        state["contract_satisfied"] = valid_materials[-1]
    return {
        "valid": bool(material_states) and all(valid_materials),
        "materials": material_states,
    }


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
        "projection": getattr(data, "type", None),
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
    if state["projection"] != "PERSP":
        _issue(
            issues,
            "PHOTO_CAMERA_PROJECTION",
            "camera.data.type",
            "Photographic shots require perspective projection.",
            expected="PERSP",
            actual=state["projection"],
        )
    if state["sensor_width"] is None or not math.isclose(float(state["sensor_width"]), 36.0, abs_tol=1e-6):
        _issue(
            issues,
            "PHOTO_CAMERA_SENSOR",
            "sensor_width",
            "Camera sensor width must be 36 mm.",
            expected=36.0,
            actual=state["sensor_width"],
        )
    if state["lens"] is None or not 24.0 <= float(state["lens"]) <= 85.0:
        _issue(
            issues,
            "PHOTO_CAMERA_LENS",
            "lens",
            "Camera lens must be between 24 and 85 mm.",
            expected=[24.0, 85.0],
            actual=state["lens"],
        )
    if state["height_m"] < 0.01 or state["height_m"] > 0.08:
        _issue(
            issues,
            "PHOTO_CAMERA_HEIGHT",
            "location.z",
            "Camera height must be 1 to 8 cm above the floor.",
            expected=[0.01, 0.08],
            actual=state["height_m"],
        )
    if state["dof_enabled"] is not True:
        _issue(issues, "PHOTO_CAMERA_DOF", "dof.use_dof", "Depth of field must be enabled.")
    expected_fstop = 11.0 if shot_type == "WIDE" else None
    if expected_fstop is not None:
        if not math.isclose(float(state["aperture_fstop"] or 0.0), expected_fstop, abs_tol=1e-6):
            _issue(
                issues,
                "PHOTO_CAMERA_FSTOP",
                "aperture_fstop",
                "Wide establishing shots require f/11.",
                expected=11.0,
                actual=state["aperture_fstop"],
            )
    elif state["aperture_fstop"] is None or not 2.8 <= float(state["aperture_fstop"]) <= 5.6:
        _issue(
            issues,
            "PHOTO_CAMERA_FSTOP",
            "aperture_fstop",
            "Character shots require f/2.8 to f/5.6.",
            expected=[2.8, 5.6],
            actual=state["aperture_fstop"],
        )
    if state["aperture_blades"] != 0:
        _issue(
            issues,
            "PHOTO_CAMERA_APERTURE",
            "aperture_blades",
            "The photographic camera must use a round aperture.",
            expected=0,
            actual=state["aperture_blades"],
        )
    focus_target = getattr(dof, "focus_object", None)
    if focus_target is None:
        _issue(
            issues, "PHOTO_CAMERA_FOCUS_MISSING", "focus_object", "Depth of field must focus on the character's eyes."
        )
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
    noise_modifiers = []
    for _, curve in action_fcurves(camera):
        if getattr(curve, "data_path", None) in {"location", "rotation_euler"}:
            curves.append(curve)
            for modifier in getattr(curve, "modifiers", ()):
                if str(getattr(modifier, "type", "")).upper() == "NOISE":
                    noise_modifiers.append(
                        {
                            "data_path": getattr(curve, "data_path", None),
                            "array_index": getattr(curve, "array_index", 0),
                        }
                    )
    if noise_modifiers:
        _issue(
            issues,
            "PHOTO_CAMERA_SHAKE",
            "animation",
            "Remove Noise modifiers from camera location and rotation curves.",
            expected="no Noise modifiers",
            actual=noise_modifiers,
        )
    if not curves:
        _issue(issues, "PHOTO_CAMERA_ANIMATION_MISSING", "animation", "Every shot requires an eased camera move.")
        return state
    start, end = frame_range
    if not any(
        _keyframe_frame(point) is not None for curve in curves for point in getattr(curve, "keyframe_points", ())
    ):
        _issue(
            issues, "PHOTO_CAMERA_KEYS_MISSING", "animation", "Camera animation curves contain no readable keyframes."
        )
        return state
    required_frames = (start - 1, start, end, end + 1)
    for path in ("location", "rotation_euler"):
        path_curves = [curve for curve in curves if getattr(curve, "data_path", None) == path]
        path_points = [point for curve in path_curves for point in getattr(curve, "keyframe_points", ())]
        actual_frames = [_keyframe_frame(point) for point in path_points]
        actual_frames = [frame for frame in actual_frames if frame is not None]
        missing_frames = [
            expected
            for expected in required_frames
            if not any(math.isclose(frame, expected, abs_tol=1e-4) for frame in actual_frames)
        ]
        if missing_frames:
            _issue(
                issues,
                "PHOTO_CAMERA_ENDPOINT_EXTENSION",
                f"{path}_keyframe_frames",
                f"{path} animation must contain every shot endpoint and one frame beyond each end.",
                expected=list(required_frames),
                actual=sorted(set(actual_frames)),
            )
        if any(getattr(point, "interpolation", None) != "BEZIER" for point in path_points):
            _issue(
                issues,
                "PHOTO_CAMERA_EASING",
                f"{path}_interpolation",
                "All camera motion keyframes must use BEZIER interpolation.",
                expected="BEZIER",
                actual=sorted({getattr(point, "interpolation", None) for point in path_points}),
            )
        if path == "rotation_euler":
            values = [_keyframe_value(point) for point in path_points]
            values = [value for value in values if value is not None]
            if any(abs(second - first) > math.pi for first, second in zip(values, values[1:])):
                _issue(
                    issues,
                    "PHOTO_CAMERA_ROTATION_DISCONTINUITY",
                    "rotation_euler",
                    "Camera Euler rotation jumps more than 180 degrees between keys.",
                )
    return state


def _dimensions(obj: Any | None) -> list[float] | None:
    if obj is None:
        return None
    dimensions = getattr(obj, "dimensions", None)
    if dimensions is None:
        return None
    try:
        values = [float(value) for value in dimensions]
    except (TypeError, ValueError):
        try:
            values = [float(getattr(dimensions, axis)) for axis in ("x", "y", "z")]
        except (AttributeError, TypeError, ValueError):
            return None
    return values if len(values) == 3 and all(math.isfinite(value) for value in values) else None


def _bevel_state(obj: Any | None) -> dict[str, Any]:
    modifiers = (
        [modifier for modifier in getattr(obj, "modifiers", ()) if getattr(modifier, "type", None) == "BEVEL"]
        if obj is not None
        else []
    )
    bevels = [
        {
            "name": getattr(modifier, "name", None),
            "width_m": getattr(modifier, "width", None),
            "offset_type": getattr(modifier, "offset_type", None),
            "segments": getattr(modifier, "segments", None),
            "limit_method": getattr(modifier, "limit_method", None),
            "affect": getattr(modifier, "affect", None),
            "show_render": getattr(modifier, "show_render", None),
        }
        for modifier in modifiers
    ]
    valid = any(
        getattr(modifier, "offset_type", None) in {"OFFSET", "WIDTH", "DEPTH", "ABSOLUTE"}
        and 0.0003 <= float(getattr(modifier, "width", 0.0)) <= 0.0007
        and int(getattr(modifier, "segments", 0)) == 3
        and getattr(modifier, "limit_method", None) == "NONE"
        and getattr(modifier, "show_render", True) is True
        and getattr(modifier, "affect", "EDGES") == "EDGES"
        for modifier in modifiers
    )
    return {"bevels": bevels, "contract_satisfied": valid}


def _validate_toy_bevel(obj: Any | None, object_name: str, issues: list[dict]) -> dict[str, Any]:
    state = {"name": getattr(obj, "name", object_name), "type": getattr(obj, "type", None)}
    if obj is None:
        _issue(issues, "PHOTO_TOY_OBJECT_MISSING", object_name, "The requested toy object was not found.")
        state.update(_bevel_state(None))
        return state
    if getattr(obj, "type", None) != "MESH":
        _issue(issues, "PHOTO_TOY_OBJECT_TYPE", object_name, "Every toy part must be a mesh object.")
        state.update(_bevel_state(obj))
        return state
    state.update(_bevel_state(obj))
    if not state["contract_satisfied"]:
        _issue(
            issues,
            "PHOTO_TOY_BEVEL",
            object_name,
            "Every toy edge needs a render-visible 0.3 to 0.7 mm, three-segment bevel.",
            expected={
                "width_m": [0.0003, 0.0007],
                "offset_type": ["OFFSET", "WIDTH", "DEPTH", "ABSOLUTE"],
                "segments": 3,
                "limit_method": "NONE",
                "show_render": True,
                "affect": "EDGES",
            },
            actual=state["bevels"],
        )
    return state


def _validate_toy_surface(
    obj: Any | None,
    object_name: str,
    issues: list[dict],
    require_pbr_textures: bool,
) -> dict[str, Any]:
    state = {"name": getattr(obj, "name", object_name)}
    if not require_pbr_textures or obj is None or getattr(obj, "type", None) != "MESH":
        return state
    state["pbr"] = _pbr_surface_state(obj)
    if not state["pbr"]["valid"]:
        _issue(
            issues,
            "PHOTO_TOY_PBR",
            object_name,
            "The toy surface must use Poly Haven diffuse, roughness, and GL normal maps with object-space box projection and blend 0.25.",
            expected={
                "maps": list(PBR_MAPS),
                "texture_source": "Poly Haven",
                "projection": "BOX",
                "projection_blend": 0.25,
                "coordinates": "Object",
            },
            actual=state["pbr"],
        )
    return state


def _validate_surface(
    obj: Any | None,
    role: str,
    issues: list[dict],
    minimum_dimension_m: float | None = None,
    require_pbr_textures: bool = False,
) -> dict[str, Any]:
    state = {"name": getattr(obj, "name", None), "type": getattr(obj, "type", None) if obj else None}
    if obj is None:
        _issue(issues, "PHOTO_SURFACE_MISSING", role, f"The {role} object was not found.")
        return state
    if getattr(obj, "type", None) != "MESH":
        _issue(
            issues, "PHOTO_SURFACE_TYPE", role, f"The {role} must be a mesh object.", actual=getattr(obj, "type", None)
        )
        return state
    state["dimensions_m"] = _dimensions(obj)
    if minimum_dimension_m is not None and (
        state["dimensions_m"] is None or max(state["dimensions_m"]) < minimum_dimension_m
    ):
        _issue(
            issues,
            "PHOTO_ENVIRONMENT_SCALE",
            role,
            f"The {role} must have at least one life-size dimension of {minimum_dimension_m:g} m.",
            expected=f">= {minimum_dimension_m:g} m",
            actual=state["dimensions_m"],
        )
    state["has_node_material"] = _has_node_material(obj)
    state["has_texture_material"] = _has_texture_material(obj)
    if not state["has_node_material"]:
        _issue(issues, "PHOTO_SURFACE_MATERIAL", role, f"The {role} needs a node-based material.")
    if not state["has_texture_material"]:
        _issue(issues, "PHOTO_SURFACE_TEXTURE", role, f"The {role} must use a textured or scanned surface material.")
    if require_pbr_textures:
        state["pbr"] = _pbr_surface_state(obj)
        if not state["pbr"]["valid"]:
            _issue(
                issues,
                "PHOTO_SURFACE_PBR",
                role,
                f"The {role} must use Poly Haven diffuse, roughness, and GL normal maps with object-space box projection and blend 0.25.",
                expected={
                    "maps": list(PBR_MAPS),
                    "texture_source": "Poly Haven",
                    "projection": "BOX",
                    "projection_blend": 0.25,
                    "coordinates": "Object",
                },
                actual=state["pbr"],
            )
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
    device_backend: str = "AUTO",
    scene_kind: str = "EXTERIOR",
    toy_object_names: list[str] | tuple[str, ...] | None = None,
    minimum_environment_dimension_m: float = 1.0,
    preview_still_path: str | None = None,
    require_post: bool = True,
    require_preview_still: bool = True,
    require_pbr_textures: bool = True,
) -> dict:
    """Run machine-readable checks for the prompt's complete shot contract."""
    try:
        shot = str(shot_type or "CHARACTER").strip().upper()
        if shot not in {"CHARACTER", "WIDE"}:
            raise ValueError("shot_type must be CHARACTER or WIDE")
        profile = str(profile_name or "FINAL").strip().upper()
        if profile not in {"PREVIEW", "FINAL"}:
            raise ValueError("profile_name must be PREVIEW or FINAL")
        kind = str(scene_kind or "EXTERIOR").strip().upper()
        if kind not in {"EXTERIOR", "INTERIOR"}:
            raise ValueError("scene_kind must be EXTERIOR or INTERIOR")
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
        if (
            isinstance(minimum_environment_dimension_m, bool)
            or not isinstance(minimum_environment_dimension_m, (int, float))
            or not math.isfinite(float(minimum_environment_dimension_m))
            or float(minimum_environment_dimension_m) <= 0.0
        ):
            raise ValueError("minimum_environment_dimension_m must be a finite number greater than zero")
        if toy_object_names is not None:
            if isinstance(toy_object_names, (str, bytes)) or not isinstance(toy_object_names, (list, tuple)):
                raise ValueError("toy_object_names must be an array of object names")
            if any(not isinstance(name, str) or not name.strip() for name in toy_object_names):
                raise ValueError("toy_object_names must contain non-empty object names")
        if not isinstance(require_post, bool) or not isinstance(require_preview_still, bool):
            raise ValueError("require_post and require_preview_still must be booleans")
        if not isinstance(require_pbr_textures, bool):
            raise ValueError("require_pbr_textures must be a boolean")

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

        required_references = {
            "hero_object": hero_object,
            "focus_object": focus_object,
            "background_object": background_object,
            "floor_object": floor_object,
            "wall_object": wall_object,
            "source_name": source_name,
        }
        for field, value in required_references.items():
            if not isinstance(value, str) or not value.strip():
                _issue(
                    issues,
                    "PHOTO_REQUIRED_REFERENCE_MISSING",
                    field,
                    f"The complete shot validator requires {field}.",
                    expected="non-empty object or source name",
                    actual=value,
                )

        unit_settings = getattr(scene, "unit_settings", None)
        units = {
            "system": getattr(unit_settings, "system", None),
            "scale_length": getattr(unit_settings, "scale_length", None),
            "length_unit": getattr(unit_settings, "length_unit", None),
        }
        if (
            units["system"] != "METRIC"
            or units["scale_length"] is None
            or not math.isclose(float(units["scale_length"]), 1.0, abs_tol=1e-6)
        ):
            _issue(
                issues,
                "PHOTO_SCENE_UNITS",
                "unit_settings",
                "The scene must use metres at unit scale 1.0.",
                expected={"system": "METRIC", "scale_length": 1.0},
                actual=units,
            )

        camera_state = (
            _validate_camera(scene, camera, focus, shot, float(floor_z), active_range, issues) if camera else None
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

        if hero_object and hero is None:
            _issue(issues, "PHOTO_HERO_MISSING", "hero_object", "The requested hero object was not found.")

        hero_state = {"name": getattr(hero, "name", hero_object)}
        if hero is not None:
            if getattr(hero, "type", None) != "MESH":
                _issue(issues, "PHOTO_HERO_TYPE", "hero_object", "The hero must be a mesh object.")
            dimensions = _dimensions(hero)
            maximum_dimension = max(dimensions) if dimensions else None
            hero_state["maximum_dimension_m"] = maximum_dimension
            if maximum_dimension is None or not 0.025 <= maximum_dimension <= 0.067:
                _issue(
                    issues,
                    "PHOTO_HERO_SCALE",
                    "hero_object",
                    "The hero must be 25 to 67 mm tall or wide.",
                    expected=[0.025, 0.067],
                    actual=maximum_dimension,
                )
            if not _has_node_material(hero):
                _issue(issues, "PHOTO_HERO_MATERIAL", "hero_object", "The hero needs a node-based material.")
            hero_bevel = _bevel_state(hero)
            hero_state["bevels"] = hero_bevel["bevels"]
            hero_state["bevel_contract_satisfied"] = hero_bevel["contract_satisfied"]

        toy_names = [hero_object] if hero_object else []
        if toy_object_names is not None:
            toy_names.extend(toy_object_names)
        toy_states = []
        seen_toys: set[str] = set()
        for object_name in toy_names:
            if object_name in seen_toys:
                continue
            seen_toys.add(object_name)
            toy_states.append(_validate_toy_bevel(_object(bpy, object_name), object_name, issues))
            toy_states[-1].update(
                _validate_toy_surface(_object(bpy, object_name), object_name, issues, require_pbr_textures)
            )

        surfaces = {}
        if floor_object:
            surfaces["floor"] = _validate_surface(
                floor,
                "floor",
                issues,
                float(minimum_environment_dimension_m),
                require_pbr_textures,
            )
        if wall_object:
            surfaces["wall"] = _validate_surface(
                wall,
                "wall",
                issues,
                float(minimum_environment_dimension_m),
                require_pbr_textures,
            )
        if background_object and background is None:
            _issue(issues, "PHOTO_BACKGROUND_MISSING", "background_object", "The background object was not found.")
        elif background_object:
            surfaces["background"] = _validate_surface(
                background,
                "background",
                issues,
                float(minimum_environment_dimension_m),
                require_pbr_textures,
            )

        hidden_animation = []
        for obj in getattr(bpy.data, "objects", ()):
            for _, curve in action_fcurves(obj):
                if getattr(curve, "data_path", None) == "hide_render":
                    hidden_animation.append(getattr(obj, "name", None))
        if hidden_animation:
            _issue(
                issues,
                "PHOTO_HIDE_RENDER_ANIMATED",
                "hide_render",
                "Shot switching must not animate object.hide_render.",
                objects=hidden_animation,
            )

        requested_backend = str(device_backend or "AUTO").strip().upper()
        if requested_backend == "AUTO" and str(getattr(getattr(scene, "cycles", None), "device", "")).upper() == "CPU":
            requested_backend = "CPU"
        profile_report = validate_render_profile(
            profile_name=profile,
            scene_kind=kind,
            device_backend=requested_backend,
            samples=getattr(getattr(scene, "cycles", None), "samples", None),
            scene_name=getattr(scene, "name", scene_name),
            allow_cpu_fallback=False,
        )
        if not profile_report.get("success") or profile_report.get("context", {}).get("valid") is False:
            _issue(
                issues,
                "PHOTO_RENDER_PROFILE",
                "render_profile",
                "The selected photographic render profile is invalid.",
                details=profile_report.get("context", {}),
            )
        profile_context = profile_report.get("context", {})
        resolved_backend = str(profile_context.get("resolved_device_backend", "")).upper()
        if profile_report.get("success") and resolved_backend not in PHOTOGRAPHIC_GPU_BACKENDS:
            _issue(
                issues,
                "PHOTO_GPU_BACKEND",
                "device_backend",
                "The photographic prompt requires OptiX on NVIDIA or Metal on macOS.",
                expected=sorted(PHOTOGRAPHIC_GPU_BACKENDS),
                actual=resolved_backend or None,
            )
        if (
            profile == "FINAL"
            and require_preview_still
            and (not isinstance(preview_still_path, str) or not preview_still_path.strip())
        ):
            _issue(
                issues,
                "PHOTO_PREVIEW_STILL_MISSING",
                "preview_still_path",
                "Render and analyze a 25% / 32-sample preview still before final validation.",
                expected="readable local preview still path",
                actual=preview_still_path,
            )
        if (
            profile == "FINAL"
            and require_preview_still
            and isinstance(preview_still_path, str)
            and preview_still_path.strip()
        ):
            preview_path = Path(preview_still_path).expanduser().resolve()
            if not preview_path.is_file():
                _issue(
                    issues,
                    "PHOTO_PREVIEW_STILL_UNREADABLE",
                    "preview_still_path",
                    "The preview still must be a readable local file.",
                    expected=str(preview_path),
                    actual=None,
                )
            preview_metadata_path = _preview_metadata_path(preview_still_path)
            preview_metadata = _read_preview_metadata(preview_metadata_path)
            if preview_metadata is None:
                _issue(
                    issues,
                    "PHOTO_PREVIEW_METADATA_MISSING",
                    "preview_still_path",
                    "The preview must be produced by render_photographic_test_still with 25% resolution and 32 samples.",
                    expected={"profile_name": "PREVIEW", "resolution_percentage": 25, "samples": 32},
                    actual=str(preview_metadata_path),
                )
            else:
                expected_preview = {
                    "contract": "dcc-mcp-blender.photographic-preview.v1",
                    "still_path": str(preview_path),
                    "profile_name": "PREVIEW",
                    "resolution_percentage": 25,
                    "samples": 32,
                    "file_format": "JPEG",
                }
                mismatches = {
                    key: {"expected": value, "actual": preview_metadata.get(key)}
                    for key, value in expected_preview.items()
                    if preview_metadata.get(key) != value
                }
                if mismatches:
                    _issue(
                        issues,
                        "PHOTO_PREVIEW_METADATA_MISMATCH",
                        "preview_still_path",
                        "The preview metadata does not match the 25% / 32-sample JPEG contract.",
                        expected=expected_preview,
                        actual=mismatches,
                    )
                if str(preview_metadata.get("device_backend", "")).upper() not in PHOTOGRAPHIC_GPU_BACKENDS:
                    _issue(
                        issues,
                        "PHOTO_PREVIEW_GPU_BACKEND",
                        "preview_still_path",
                        "The preview must be rendered with OptiX or Metal.",
                        expected=sorted(PHOTOGRAPHIC_GPU_BACKENDS),
                        actual=preview_metadata.get("device_backend"),
                    )
        post_report = None
        if require_post:
            post_report = validate_photographic_post(
                scene_name=getattr(scene, "name", scene_name),
                require_prompt_defaults=True,
            )
            if not post_report.get("success") or post_report.get("context", {}).get("valid") is False:
                _issue(
                    issues,
                    "PHOTO_POST_STACK",
                    "post",
                    "The photographic compositor finish is invalid.",
                    details=post_report.get("context", {}),
                )
        lighting_report = None
        if source_name:
            lighting_report = validate_motivated_lighting(
                source_name=source_name,
                source_type=source_type,
                hero_object=hero_object,
                background_object=background_object,
                preview_still_path=preview_still_path,
                require_polyhaven_hdri=True,
            )
            lighting_context = lighting_report.get("context", {})
            if not lighting_report.get("success") or lighting_context.get("valid") is False:
                _issue(
                    issues,
                    "PHOTO_LIGHTING_CONTRACT",
                    "lighting",
                    "The motivated lighting contract is invalid.",
                    details=lighting_context,
                )
            elif any(
                issue.get("code") == "HERO_BACKGROUND_CONTRAST_MISSING" for issue in lighting_context.get("issues", [])
            ):
                _issue(
                    issues,
                    "PHOTO_HERO_BACKGROUND_CONTRAST",
                    "lighting",
                    "The hero must be in front of something darker or cooler.",
                    details=lighting_context.get("hero_background"),
                )
            if any(issue.get("code") == "WARM_SATURATED_HIGHLIGHTS" for issue in lighting_context.get("issues", [])):
                _issue(
                    issues,
                    "PHOTO_LIGHTING_COLOR_SAFETY",
                    "lighting",
                    "Lower the motivated key energy until saturated colors remain safe under AgX.",
                    details=lighting_context.get("color_safety"),
                )

        return skill_success(
            "Photographic shot validation completed",
            valid=not issues,
            issues=issues,
            scene_name=getattr(scene, "name", scene_name),
            frame_range=list(active_range),
            shot_type=shot,
            profile_name=profile,
            scene_kind=kind,
            device_backend=requested_backend,
            units=units,
            camera=camera_state,
            focus_object=getattr(focus, "name", focus_object),
            hero=hero_state,
            toy_objects=toy_states,
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
