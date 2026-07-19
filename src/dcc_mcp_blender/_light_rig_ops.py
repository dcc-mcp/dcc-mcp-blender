"""Blender light rig and environment setup helpers."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

RIG_PROP = "dcc_mcp_light_rig"
ORIGINAL_ENERGY_PROP = "dcc_mcp_original_energy"
HDRI_ENV_NODE = "DCC MCP HDRI"
HDRI_MAPPING_NODE = "DCC MCP Mapping"
HDRI_TEXCOORD_NODE = "DCC MCP Texture Coordinate"
HDRI_ROTATION_INTERPOLATIONS = {"BEZIER", "CONSTANT", "LINEAR"}


def _iter_collection(collection: Any) -> List[Any]:
    try:
        return list(collection)
    except TypeError:
        return []


def _collection_get(collection: Any, name: str) -> Any:
    getter = getattr(collection, "get", None)
    if callable(getter):
        return getter(name)
    for item in _iter_collection(collection):
        if getattr(item, "name", None) == name:
            return item
    return None


def _custom_get(target: Any, key: str, default: Any = None) -> Any:
    getter = getattr(target, "get", None)
    if callable(getter):
        return getter(key, default)
    try:
        return target[key]
    except Exception:
        return default


def _custom_set(target: Any, key: str, value: Any) -> None:
    try:
        target[key] = value
    except Exception:
        setattr(target, key, value)


def _safe_path(image_path: str) -> Tuple[Optional[Path], Optional[dict]]:
    raw = str(image_path or "").strip()
    if not raw:
        return None, skill_error("Missing image path", "Pass a local HDRI/image path.")
    if "://" in raw or raw.startswith("\\\\"):
        return None, skill_error("Unsafe image path", "Use a local filesystem path, not a URL or UNC path.")
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        return None, skill_error(f"Image not found: {path}", f"No image exists at '{path}'.")
    return path, None


def _vec(value: Optional[List[float]], fallback: Tuple[float, float, float]) -> List[float]:
    if value is None:
        return [float(item) for item in fallback]
    if len(value) != 3:
        raise ValueError("Vector values must have exactly 3 numbers.")
    return [float(item) for item in value]


def _rgb(value: Optional[List[float]], fallback: Tuple[float, float, float] = (1.0, 1.0, 1.0)) -> List[float]:
    if value is None:
        return [float(item) for item in fallback]
    if len(value) not in (3, 4):
        raise ValueError("Color values must have 3 or 4 numbers.")
    return [float(item) for item in value[:3]]


def _ensure_collection(bpy: Any, name: str) -> Any:
    collection = _collection_get(bpy.data.collections, name)
    if collection is not None:
        return collection
    collection = bpy.data.collections.new(name)
    children = getattr(getattr(bpy.context.scene, "collection", None), "children", None)
    linker = getattr(children, "link", None)
    if callable(linker):
        linker(collection)
    return collection


def _link_object(collection: Any, obj: Any) -> None:
    objects = getattr(collection, "objects", None)
    linker = getattr(objects, "link", None)
    if callable(linker):
        try:
            linker(obj)
        except Exception:
            pass


def _create_light_object(
    bpy: Any,
    name: str,
    light_type: str,
    location: List[float],
    energy: float,
    color: Optional[List[float]] = None,
    size: Optional[float] = None,
    rotation: Optional[List[float]] = None,
    collection: Any = None,
) -> Any:
    light_data = bpy.data.lights.new(name=name, type=light_type)
    light_data.energy = float(energy)
    if color is not None:
        light_data.color = _rgb(color)
    if size is not None:
        if hasattr(light_data, "size"):
            light_data.size = float(size)
        if hasattr(light_data, "shadow_soft_size"):
            light_data.shadow_soft_size = float(size)
    obj = bpy.data.objects.new(name=name, object_data=light_data)
    obj.location = location
    if rotation is not None:
        obj.rotation_euler = rotation
    _custom_set(obj, ORIGINAL_ENERGY_PROP, float(energy))
    if collection is not None:
        _link_object(collection, obj)
    else:
        bpy.context.scene.collection.objects.link(obj)
    return obj


def _light_info(obj: Any) -> Dict[str, Any]:
    return {
        "name": getattr(obj, "name", None),
        "light_type": getattr(getattr(obj, "data", None), "type", None),
        "energy": getattr(getattr(obj, "data", None), "energy", None),
        "color": list(getattr(getattr(obj, "data", None), "color", []) or []),
        "location": list(getattr(obj, "location", []) or []),
    }


def _rig_payload(name: str, light_names: List[str]) -> Dict[str, Any]:
    return {"name": name, "lights": light_names}


def _store_rig(collection: Any, name: str, light_names: List[str]) -> None:
    _custom_set(collection, RIG_PROP, json.dumps(_rig_payload(name, light_names), sort_keys=True))


def _load_rig(collection: Any) -> Optional[Dict[str, Any]]:
    raw = _custom_get(collection, RIG_PROP, None)
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        payload = json.loads(str(raw))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _rig_collections(bpy: Any) -> List[Tuple[Any, Dict[str, Any]]]:
    rigs = []
    for collection in _iter_collection(bpy.data.collections):
        payload = _load_rig(collection)
        if payload:
            rigs.append((collection, payload))
    return rigs


def _find_rig(bpy: Any, rig_name: str) -> Tuple[Any, Optional[Dict[str, Any]]]:
    for collection, payload in _rig_collections(bpy):
        if payload.get("name") == rig_name or getattr(collection, "name", None) == rig_name:
            return collection, payload
    return None, None


def _aim_at(light: Any, target: Any) -> None:
    _custom_set(light, "dcc_mcp_aim_target", getattr(target, "name", None))
    try:
        from mathutils import Vector

        direction = Vector(target.location) - Vector(light.location)
        if direction.length == 0:
            return
        light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    except Exception:
        return


def _world_info(world: Any) -> Dict[str, Any]:
    if world is None:
        return {}
    info = {
        "name": getattr(world, "name", None),
        "color": list(getattr(world, "color", []) or []),
        "use_nodes": bool(getattr(world, "use_nodes", False)),
    }
    node_tree = getattr(world, "node_tree", None)
    nodes = getattr(node_tree, "nodes", None)
    env = _collection_get(nodes, HDRI_ENV_NODE) if nodes is not None else None
    mapping = _collection_get(nodes, HDRI_MAPPING_NODE) if nodes is not None else None
    if env is None or mapping is None:
        return info
    background = _collection_get(nodes, "Background")
    strength_socket = _collection_get(getattr(background, "inputs", {}), "Strength")
    coordinate_output = None
    for link in _iter_collection(getattr(node_tree, "links", [])):
        to_node_name = getattr(getattr(link, "to_node", None), "name", None)
        to_socket_name = getattr(getattr(link, "to_socket", None), "name", None)
        if to_node_name == getattr(mapping, "name", None) and to_socket_name == "Vector":
            coordinate_output = getattr(getattr(link, "from_socket", None), "name", None)
            break
    image = getattr(env, "image", None)
    hdri = {
        "image_path": getattr(image, "filepath", None) or getattr(image, "filepath_raw", None),
        "strength": getattr(strength_socket, "default_value", None),
        "rotation": _custom_get(world, "dcc_mcp_hdri_rotation", None),
        "coordinate_output": coordinate_output,
    }
    frame_start = _custom_get(world, "dcc_mcp_hdri_animation_frame_start", None)
    if frame_start is not None:
        hdri["animation"] = {
            "frame_start": frame_start,
            "frame_end": _custom_get(world, "dcc_mcp_hdri_animation_frame_end", None),
            "start_rotation": _custom_get(world, "dcc_mcp_hdri_animation_start_rotation", None),
            "end_rotation": _custom_get(world, "dcc_mcp_hdri_animation_end_rotation", None),
            "interpolation": _custom_get(world, "dcc_mcp_hdri_animation_interpolation", None),
        }
    info["hdri"] = hdri
    return info


def _view_settings_info(view_settings: Any) -> Dict[str, Any]:
    return {
        "view_transform": getattr(view_settings, "view_transform", None),
        "look": getattr(view_settings, "look", None),
        "exposure": getattr(view_settings, "exposure", None),
        "gamma": getattr(view_settings, "gamma", None),
    }


def _set_vector_socket_value(socket: Any, values: List[float]) -> None:
    default_value = getattr(socket, "default_value", None)
    if default_value is None:
        return
    for index, value in enumerate(values):
        try:
            default_value[index] = float(value)
        except Exception:
            return


def _set_socket_keyframe_interpolation(
    node_tree: Any,
    socket: Any,
    frames: List[int],
    interpolation: str,
) -> None:
    animation_data = getattr(node_tree, "animation_data", None)
    action = getattr(animation_data, "action", None)
    fcurves = getattr(action, "fcurves", None)
    if fcurves is None:
        return
    data_path = None
    path_from_id = getattr(socket, "path_from_id", None)
    if callable(path_from_id):
        try:
            data_path = path_from_id("default_value")
        except Exception:
            data_path = None
    fcurve = None
    finder = getattr(fcurves, "find", None)
    if data_path and callable(finder):
        try:
            fcurve = finder(data_path, index=2)
        except Exception:
            fcurve = None
    if fcurve is None:
        for candidate in _iter_collection(fcurves):
            candidate_path = str(getattr(candidate, "data_path", ""))
            if HDRI_MAPPING_NODE in candidate_path and getattr(candidate, "array_index", None) == 2:
                fcurve = candidate
                break
    if fcurve is None:
        return
    expected_frames = {int(frame) for frame in frames}
    for point in _iter_collection(getattr(fcurve, "keyframe_points", [])):
        coordinates = getattr(point, "co", None)
        if coordinates is None:
            continue
        try:
            frame = int(round(float(coordinates[0])))
        except Exception:
            continue
        if frame in expected_frames:
            point.interpolation = interpolation


def create_three_point_light_rig(
    name: str,
    target_object: Optional[str] = None,
    key: Optional[Dict[str, Any]] = None,
    fill: Optional[Dict[str, Any]] = None,
    rim: Optional[Dict[str, Any]] = None,
) -> dict:
    """Create a three-point area-light rig in a dedicated collection."""
    try:
        import bpy

        target = _collection_get(bpy.data.objects, target_object) if target_object else None
        if target_object and target is None:
            return skill_error(f"Object not found: {target_object}", f"No object named '{target_object}'.")
        collection = _ensure_collection(bpy, name)
        specs = [
            ("Key", key or {}, (-3.0, -4.0, 5.0), 800.0, 4.0),
            ("Fill", fill or {}, (4.0, -3.0, 3.0), 250.0, 5.5),
            ("Rim", rim or {}, (0.0, 4.0, 4.0), 500.0, 3.0),
        ]
        lights = []
        for label, options, fallback_location, fallback_energy, fallback_size in specs:
            light = _create_light_object(
                bpy,
                f"{name}_{label}",
                str(options.get("type", "AREA")).upper(),
                _vec(options.get("location"), fallback_location),
                float(options.get("energy", fallback_energy)),
                options.get("color"),
                float(options.get("size", fallback_size)),
                collection=collection,
            )
            if target is not None:
                _aim_at(light, target)
            lights.append(light)
        _store_rig(collection, name, [light.name for light in lights])
        return skill_success(
            "Three-point light rig created",
            rig_name=name,
            collection_name=getattr(collection, "name", name),
            target_object=target_object,
            lights=[_light_info(light) for light in lights],
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except ValueError as exc:
        return skill_error("Invalid light rig option", str(exc))
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create light rig {name}")


def create_area_softbox(
    name: str,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    size: float = 5.0,
    energy: float = 500.0,
) -> dict:
    """Create one large soft area light."""
    try:
        import bpy

        light = _create_light_object(
            bpy,
            name,
            "AREA",
            _vec(location, (0.0, -3.0, 4.0)),
            float(energy),
            size=float(size),
            rotation=_vec(rotation, (1.0, 0.0, 0.0)) if rotation is not None else None,
        )
        return skill_success("Area softbox created", light=_light_info(light), size=float(size))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except ValueError as exc:
        return skill_error("Invalid softbox option", str(exc))
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create softbox {name}")


def create_hdri_world(image_path: str, strength: float = 1.0, rotation: float = 0.0) -> dict:
    """Create an environment-texture world from a local image."""
    path, error = _safe_path(image_path)
    if error:
        return error
    try:
        import bpy

        scene = bpy.context.scene
        world = scene.world or bpy.data.worlds.new(name="World")
        scene.world = world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        background = _collection_get(nodes, "Background")
        if background is None:
            background = nodes.new(type="ShaderNodeBackground")
            background.name = "Background"
        env = _collection_get(nodes, HDRI_ENV_NODE) or nodes.new(type="ShaderNodeTexEnvironment")
        env.name = HDRI_ENV_NODE
        env.image = bpy.data.images.load(str(path), check_existing=True)
        texcoord = _collection_get(nodes, HDRI_TEXCOORD_NODE) or nodes.new(type="ShaderNodeTexCoord")
        texcoord.name = HDRI_TEXCOORD_NODE
        mapping = _collection_get(nodes, HDRI_MAPPING_NODE) or nodes.new(type="ShaderNodeMapping")
        mapping.name = HDRI_MAPPING_NODE
        rotation_socket = _collection_get(getattr(mapping, "inputs", {}), "Rotation")
        if rotation_socket is not None:
            _set_vector_socket_value(rotation_socket, [0.0, 0.0, math.radians(float(rotation))])
        texcoord_output = _collection_get(getattr(texcoord, "outputs", {}), "Normal") or _collection_get(
            getattr(texcoord, "outputs", {}), "Vector"
        )
        mapping_input = _collection_get(getattr(mapping, "inputs", {}), "Vector")
        mapping_output = _collection_get(getattr(mapping, "outputs", {}), "Vector")
        env_vector = _collection_get(getattr(env, "inputs", {}), "Vector")
        if texcoord_output is not None and mapping_input is not None:
            try:
                links.new(texcoord_output, mapping_input)
            except Exception:
                pass
        if mapping_output is not None and env_vector is not None:
            try:
                links.new(mapping_output, env_vector)
            except Exception:
                pass
        color = _collection_get(getattr(env, "outputs", {}), "Color")
        bg_color = _collection_get(getattr(background, "inputs", {}), "Color")
        if color is not None and bg_color is not None:
            try:
                links.new(color, bg_color)
            except Exception:
                pass
        strength_socket = _collection_get(getattr(background, "inputs", {}), "Strength")
        if strength_socket is not None and hasattr(strength_socket, "default_value"):
            strength_socket.default_value = float(strength)
        else:
            world.strength = float(strength)
        _custom_set(world, "dcc_mcp_hdri_rotation", float(rotation))
        return skill_success(
            "HDRI world created",
            image_path=str(path),
            strength=float(strength),
            rotation=float(rotation),
            coordinate_output=getattr(texcoord_output, "name", None),
            world=_world_info(world),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to create HDRI world")


def animate_hdri_rotation(
    frame_start: int,
    frame_end: int,
    start_rotation: float = 0.0,
    end_rotation: float = 360.0,
    interpolation: str = "LINEAR",
) -> dict:
    """Animate the existing HDRI mapping rotation for a fixed-camera LookDev pass."""
    try:
        import bpy

        start = int(frame_start)
        end = int(frame_end)
        if end <= start:
            return skill_error("Invalid frame range", "frame_end must be greater than frame_start.")
        mode = str(interpolation or "LINEAR").strip().upper()
        if mode not in HDRI_ROTATION_INTERPOLATIONS:
            supported = ", ".join(sorted(HDRI_ROTATION_INTERPOLATIONS))
            return skill_error("Unsupported interpolation", f"Use one of: {supported}.")
        start_degrees = float(start_rotation)
        end_degrees = float(end_rotation)
        if not math.isfinite(start_degrees) or not math.isfinite(end_degrees):
            return skill_error("Invalid HDRI rotation", "Rotation values must be finite numbers in degrees.")

        scene = bpy.context.scene
        world = getattr(scene, "world", None)
        if world is None or not getattr(world, "use_nodes", False):
            return skill_error("HDRI world not found", "Call create_hdri_world before animating HDRI rotation.")
        node_tree = getattr(world, "node_tree", None)
        nodes = getattr(node_tree, "nodes", None)
        mapping = _collection_get(nodes, HDRI_MAPPING_NODE) if nodes is not None else None
        if mapping is None:
            return skill_error("HDRI mapping not found", "Call create_hdri_world before animating HDRI rotation.")
        rotation_socket = _collection_get(getattr(mapping, "inputs", {}), "Rotation")
        if rotation_socket is None or getattr(rotation_socket, "default_value", None) is None:
            return skill_error("HDRI rotation unavailable", "The HDRI mapping node has no Rotation input.")
        insert_keyframe = getattr(rotation_socket, "keyframe_insert", None)
        if not callable(insert_keyframe):
            return skill_error("HDRI rotation cannot be animated", "The Rotation input does not support keyframes.")

        original_frame = int(getattr(scene, "frame_current", start))
        keyframes = [
            {"frame": start, "rotation": start_degrees},
            {"frame": end, "rotation": end_degrees},
        ]
        try:
            for keyframe in keyframes:
                _set_vector_socket_value(
                    rotation_socket,
                    [0.0, 0.0, math.radians(float(keyframe["rotation"]))],
                )
                inserted = insert_keyframe(data_path="default_value", index=2, frame=keyframe["frame"])
                if inserted is False:
                    return skill_error(
                        "Failed to keyframe HDRI rotation",
                        f"Blender rejected the keyframe at frame {keyframe['frame']}.",
                    )
            _set_socket_keyframe_interpolation(
                node_tree,
                rotation_socket,
                [start, end],
                mode,
            )
        finally:
            frame_set = getattr(scene, "frame_set", None)
            if callable(frame_set):
                frame_set(original_frame)

        _custom_set(world, "dcc_mcp_hdri_animation_frame_start", start)
        _custom_set(world, "dcc_mcp_hdri_animation_frame_end", end)
        _custom_set(world, "dcc_mcp_hdri_animation_start_rotation", start_degrees)
        _custom_set(world, "dcc_mcp_hdri_animation_end_rotation", end_degrees)
        _custom_set(world, "dcc_mcp_hdri_animation_interpolation", mode)
        return skill_success(
            "HDRI rotation animated",
            keyframes=keyframes,
            interpolation=mode,
            mapping_node=HDRI_MAPPING_NODE,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid HDRI animation option", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to animate HDRI rotation")


def list_light_rigs() -> dict:
    """List light rigs created by this skill."""
    try:
        import bpy

        rigs = []
        for collection, payload in _rig_collections(bpy):
            light_names = list(payload.get("lights", []))
            rigs.append(
                {
                    "rig_name": payload.get("name", getattr(collection, "name", None)),
                    "collection_name": getattr(collection, "name", None),
                    "lights": light_names,
                    "light_count": len(light_names),
                }
            )
        return skill_success("Light rigs listed", rigs=rigs, count=len(rigs))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list light rigs")


def set_light_rig_intensity(rig_name: str, multiplier: float) -> dict:
    """Scale every light in a rig from its original energy."""
    try:
        import bpy

        _collection, payload = _find_rig(bpy, rig_name)
        if payload is None:
            return skill_error(f"Light rig not found: {rig_name}", "Create or group a rig before scaling it.")
        updated = []
        for light_name in payload.get("lights", []):
            light = _collection_get(bpy.data.objects, light_name)
            if light is None or getattr(light, "type", None) != "LIGHT":
                continue
            original = _custom_get(light, ORIGINAL_ENERGY_PROP, getattr(light.data, "energy", 0.0))
            light.data.energy = float(original) * float(multiplier)
            updated.append(_light_info(light))
        return skill_success(
            "Light rig intensity updated", rig_name=rig_name, multiplier=float(multiplier), lights=updated
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set light rig intensity for {rig_name}")


def aim_light_at_object(light_name: str, target_object: str) -> dict:
    """Aim one light at a target object."""
    try:
        import bpy

        light = _collection_get(bpy.data.objects, light_name)
        if light is None:
            return skill_error(f"Light not found: {light_name}", f"No object named '{light_name}'.")
        if getattr(light, "type", None) != "LIGHT":
            return skill_error(f"{light_name} is not a light", "Expected an object of type LIGHT.")
        target = _collection_get(bpy.data.objects, target_object)
        if target is None:
            return skill_error(f"Object not found: {target_object}", f"No object named '{target_object}'.")
        _aim_at(light, target)
        return skill_success("Light aimed at object", light_name=light_name, target_object=target_object)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to aim light {light_name}")


def group_lights(light_names: List[str], collection_name: str) -> dict:
    """Group existing light objects into a rig collection."""
    try:
        import bpy

        lights = []
        for light_name in light_names:
            light = _collection_get(bpy.data.objects, light_name)
            if light is None:
                return skill_error(f"Light not found: {light_name}", f"No object named '{light_name}'.")
            if getattr(light, "type", None) != "LIGHT":
                return skill_error(f"{light_name} is not a light", "Only LIGHT objects can be grouped.")
            lights.append(light)
        collection = _ensure_collection(bpy, collection_name)
        for light in lights:
            _link_object(collection, light)
            _custom_set(light, ORIGINAL_ENERGY_PROP, float(getattr(light.data, "energy", 0.0)))
        _store_rig(collection, collection_name, [light.name for light in lights])
        return skill_success(
            "Lights grouped",
            rig_name=collection_name,
            collection_name=getattr(collection, "name", collection_name),
            lights=[_light_info(light) for light in lights],
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to group lights into {collection_name}")


def set_render_view_transform(
    view_transform: Optional[str] = None,
    look: Optional[str] = None,
    exposure: Optional[float] = None,
    gamma: Optional[float] = None,
) -> dict:
    """Set scene view transform and exposure controls."""
    try:
        import bpy

        view_settings = getattr(bpy.context.scene, "view_settings", None)
        if view_settings is None:
            return skill_error("Render view settings unavailable", "Scene view_settings is not available.")
        try:
            if view_transform is not None:
                view_settings.view_transform = view_transform
            if look is not None:
                view_settings.look = look
            if exposure is not None:
                view_settings.exposure = float(exposure)
            if gamma is not None:
                view_settings.gamma = float(gamma)
        except Exception as exc:
            return skill_error("Unsupported render view setting", str(exc))
        return skill_success("Render view transform updated", current=_view_settings_info(view_settings))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set render view transform")


def get_lighting_summary() -> dict:
    """Return lights, rig, world, and render-view summary."""
    try:
        import bpy

        lights = [
            _light_info(obj) for obj in _iter_collection(bpy.data.objects) if getattr(obj, "type", None) == "LIGHT"
        ]
        rigs = list_light_rigs()
        return skill_success(
            "Lighting summary retrieved",
            lights=lights,
            light_count=len(lights),
            rigs=rigs.get("context", {}).get("rigs", []),
            world=_world_info(getattr(bpy.context.scene, "world", None)),
            view_settings=_view_settings_info(getattr(bpy.context.scene, "view_settings", None)),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to get lighting summary")
