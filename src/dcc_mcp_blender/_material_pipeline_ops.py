"""Blender material library, image, color-management, and texture bake helpers."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._node_graph_ops import (
    _collection_get,
    _ensure_material_nodes,
    _find_principled_node,
    _get_socket,
    _iter_collection,
    _link_info,
    _node_info,
    _set_socket_value,
    _socket_items,
    _socket_value,
    assign_texture_node,
)

MATERIAL_PRESETS_KEY = "dcc_mcp_material_presets"
MATERIAL_PRESET_SCHEMA = "dcc-mcp-blender.material-preset.v1"
SUPPORTED_BAKE_MAPS = {
    "diffuse": "DIFFUSE",
    "base_color": "DIFFUSE",
    "combined": "COMBINED",
    "lighting": "COMBINED",
    "ambient_occlusion": "AO",
    "ao": "AO",
    "normal": "NORMAL",
    "roughness": "ROUGHNESS",
    "emit": "EMIT",
}
SUPPORTED_IMAGE_SUFFIXES = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".exr": "OPEN_EXR",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    try:
        return [_jsonable(item) for item in value]
    except TypeError:
        return str(value)


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


def _load_json_prop(target: Any, key: str) -> Dict[str, Any]:
    raw = _custom_get(target, key, None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        data = json.loads(str(raw))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _store_json_prop(target: Any, key: str, value: Dict[str, Any]) -> None:
    _custom_set(target, key, json.dumps(value, sort_keys=True))


def _preset_store(scene: Any) -> Dict[str, Any]:
    data = _load_json_prop(scene, MATERIAL_PRESETS_KEY)
    presets = data.get("presets", data)
    return presets if isinstance(presets, dict) else {}


def _save_preset_store(scene: Any, presets: Dict[str, Any]) -> None:
    _store_json_prop(scene, MATERIAL_PRESETS_KEY, {"schema": MATERIAL_PRESET_SCHEMA, "presets": presets})


def _safe_raw_path(raw_path: str, label: str) -> Tuple[Optional[Path], Optional[dict]]:
    raw = str(raw_path or "").strip()
    if not raw:
        return None, skill_error(f"Missing {label}", f"Pass a local {label}.")
    if "://" in raw or raw.startswith("\\\\"):
        return None, skill_error(f"Unsafe {label}", "Use a local filesystem path, not a URL or UNC path.")
    return Path(raw).expanduser().resolve(), None


def _safe_output_dir(output_dir: str) -> Tuple[Optional[Path], Optional[dict]]:
    return _safe_raw_path(output_dir, "output directory")


def _safe_output_path(output_path: str) -> Tuple[Optional[Path], Optional[dict]]:
    path, error = _safe_raw_path(output_path, "output path")
    if error or path is None:
        return None, error
    if not path.suffix:
        path = path.with_suffix(".png")
    return path, None


def _image_file_format(path: Path) -> str:
    return SUPPORTED_IMAGE_SUFFIXES.get(path.suffix.lower(), "PNG")


def _object_named(bpy: Any, object_name: str) -> Any:
    return _collection_get(bpy.data.objects, object_name)


def _material_named(bpy: Any, material_name: str) -> Any:
    return _collection_get(bpy.data.materials, material_name)


def _image_named(bpy: Any, image_name: str) -> Any:
    return _collection_get(bpy.data.images, image_name)


def _material_inputs(material: Any) -> Dict[str, Any]:
    if not getattr(material, "use_nodes", False) or getattr(material, "node_tree", None) is None:
        return {}
    node = _find_principled_node(material.node_tree.nodes)
    if node is None:
        return {}
    return {str(getattr(socket, "name", "")): _jsonable(_socket_value(socket)) for socket in _socket_items(node.inputs)}


def _material_summary(material: Any, include_nodes: bool = False) -> Dict[str, Any]:
    summary = {
        "name": getattr(material, "name", None),
        "use_nodes": bool(getattr(material, "use_nodes", False)),
        "diffuse_color": _jsonable(getattr(material, "diffuse_color", None)),
        "blend_method": getattr(material, "blend_method", None),
        "principled_inputs": _material_inputs(material),
    }
    if include_nodes and getattr(material, "use_nodes", False) and getattr(material, "node_tree", None) is not None:
        summary["nodes"] = [_node_info(node) for node in _iter_collection(material.node_tree.nodes)]
        summary["links"] = [_link_info(link) for link in _iter_collection(material.node_tree.links)]
    return summary


def _make_material_preset(material: Any, preset_name: str, include_nodes: bool) -> Dict[str, Any]:
    return {
        "schema": MATERIAL_PRESET_SCHEMA,
        "preset_name": preset_name,
        "source_material": getattr(material, "name", None),
        "created_at": _now(),
        "include_nodes": bool(include_nodes),
        "material": _material_summary(material, include_nodes=include_nodes),
    }


def _apply_material_preset(material: Any, preset: Mapping[str, Any]) -> Dict[str, Any]:
    material_data = dict(preset.get("material", {}))
    diffuse_color = material_data.get("diffuse_color")
    if diffuse_color is not None:
        try:
            material.diffuse_color = diffuse_color
        except Exception:
            pass
    if material_data.get("use_nodes") or material_data.get("principled_inputs"):
        node_tree = _ensure_material_nodes(material)
        principled = _find_principled_node(node_tree.nodes)
        if principled is not None:
            for input_name, value in dict(material_data.get("principled_inputs", {})).items():
                socket = _get_socket(principled.inputs, input_name)
                if socket is not None:
                    _set_socket_value(socket, value)
    return _material_summary(material, include_nodes=False)


def _assign_material_to_object(obj: Any, material: Any) -> None:
    data = getattr(obj, "data", None)
    materials = getattr(data, "materials", None)
    if materials is not None:
        if len(_iter_collection(materials)) == 0 and callable(getattr(materials, "append", None)):
            materials.append(material)
            return
        try:
            materials[0] = material
            return
        except Exception:
            if callable(getattr(materials, "append", None)):
                materials.append(material)
                return
    slots = _iter_collection(getattr(obj, "material_slots", []))
    if slots:
        slots[0].material = material


def _material_slot_assignments(obj: Any) -> List[Dict[str, Any]]:
    assignments = []
    slots = _iter_collection(getattr(obj, "material_slots", []))
    if slots:
        for index, slot in enumerate(slots):
            material = getattr(slot, "material", None)
            assignments.append(
                {
                    "slot": index,
                    "material_name": getattr(material, "name", None),
                    "use_nodes": bool(getattr(material, "use_nodes", False)) if material is not None else False,
                    "node_count": len(_iter_collection(getattr(getattr(material, "node_tree", None), "nodes", [])))
                    if material is not None
                    else 0,
                }
            )
        return assignments
    data = getattr(obj, "data", None)
    for index, material in enumerate(_iter_collection(getattr(data, "materials", []))):
        assignments.append(
            {
                "slot": index,
                "material_name": getattr(material, "name", None),
                "use_nodes": bool(getattr(material, "use_nodes", False)),
                "node_count": len(_iter_collection(getattr(getattr(material, "node_tree", None), "nodes", []))),
            }
        )
    return assignments


def _image_info(image: Any) -> Dict[str, Any]:
    size = getattr(image, "size", [])
    try:
        size_value = [int(size[0]), int(size[1])]
    except Exception:
        size_value = []
    colorspace = getattr(getattr(image, "colorspace_settings", None), "name", None)
    return {
        "name": getattr(image, "name", None),
        "filepath": getattr(image, "filepath", None) or getattr(image, "filepath_raw", None),
        "size": size_value,
        "colorspace": colorspace,
        "source": getattr(image, "source", None),
    }


def _view_settings_info(view_settings: Any) -> Dict[str, Any]:
    return {
        "view_transform": getattr(view_settings, "view_transform", None),
        "look": getattr(view_settings, "look", None),
        "exposure": getattr(view_settings, "exposure", None),
        "gamma": getattr(view_settings, "gamma", None),
    }


def _normalise_maps(maps: Iterable[str]) -> Tuple[List[str], List[str]]:
    normalised = []
    unsupported = []
    for item in maps:
        key = str(item).strip().lower().replace("-", "_").replace(" ", "_")
        if key in SUPPORTED_BAKE_MAPS:
            normalised.append(key)
        else:
            unsupported.append(str(item))
    return normalised, unsupported


def _ensure_mesh_object(bpy: Any, object_name: str) -> Tuple[Any, Optional[dict]]:
    obj = _object_named(bpy, object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    if getattr(obj, "type", None) != "MESH":
        return None, skill_error(f"{object_name} is not a mesh", "Texture baking requires a mesh object.")
    return obj, None


def _bake_target_info(obj: Any) -> Dict[str, Any]:
    data = getattr(obj, "data", None)
    return {
        "object_name": getattr(obj, "name", None),
        "type": getattr(obj, "type", None),
        "material_count": len(_iter_collection(getattr(data, "materials", []))),
        "uv_layer_count": len(_iter_collection(getattr(data, "uv_layers", []))),
        "supported_maps": sorted(SUPPORTED_BAKE_MAPS),
    }


def _ensure_bake_material(bpy: Any, obj: Any) -> Any:
    data = getattr(obj, "data", None)
    materials = getattr(data, "materials", None)
    existing = _iter_collection(materials)
    if existing:
        return existing[0]
    material = bpy.data.materials.new(f"{getattr(obj, 'name', 'Object')} Bake Material")
    material.use_nodes = True
    if materials is not None and callable(getattr(materials, "append", None)):
        materials.append(material)
    return material


def _create_bake_image(bpy: Any, name: str, resolution: int) -> Any:
    try:
        return bpy.data.images.new(name, width=resolution, height=resolution, alpha=True, float_buffer=False)
    except TypeError:
        return bpy.data.images.new(name, resolution, resolution)


def _attach_bake_image(material: Any, image: Any) -> None:
    node_tree = _ensure_material_nodes(material)
    node = None
    for candidate in _iter_collection(node_tree.nodes):
        if (
            getattr(candidate, "type", None) == "TEX_IMAGE"
            or getattr(candidate, "bl_idname", None) == "ShaderNodeTexImage"
        ):
            node = candidate
            break
    if node is None:
        try:
            node = node_tree.nodes.new(type="ShaderNodeTexImage")
        except TypeError:
            node = node_tree.nodes.new("ShaderNodeTexImage")
    node.name = getattr(image, "name", "Bake Image")
    node.image = image
    try:
        node_tree.nodes.active = node
    except Exception:
        pass


def _select_for_bake(bpy: Any, obj: Any, source_obj: Any = None) -> None:
    for candidate in _iter_collection(bpy.data.objects):
        selector = getattr(candidate, "select_set", None)
        if callable(selector):
            selector(False)
    if source_obj is not None and callable(getattr(source_obj, "select_set", None)):
        source_obj.select_set(True)
    if callable(getattr(obj, "select_set", None)):
        obj.select_set(True)
    try:
        bpy.context.view_layer.objects.active = obj
    except Exception:
        pass


def _save_bake_image(image: Any, path: Path) -> None:
    image.filepath_raw = str(path)
    image.file_format = _image_file_format(path)
    saver = getattr(image, "save", None)
    if callable(saver):
        saver()


def _bake_one_map(
    bpy: Any,
    obj: Any,
    map_name: str,
    path: Path,
    resolution: int,
    margin: int,
    dry_run: bool,
    source_obj: Any = None,
) -> Dict[str, Any]:
    bake_type = SUPPORTED_BAKE_MAPS[map_name]
    info = {
        "map": map_name,
        "bake_type": bake_type,
        "path": str(path),
        "resolution": int(resolution),
        "margin": int(margin),
        "dry_run": bool(dry_run),
    }
    if dry_run:
        return info

    path.parent.mkdir(parents=True, exist_ok=True)
    material = _ensure_bake_material(bpy, obj)
    image = _create_bake_image(
        bpy, f"dcc_mcp_{getattr(obj, 'name', 'object')}_{map_name}_{uuid.uuid4().hex[:8]}", resolution
    )
    _attach_bake_image(material, image)
    _select_for_bake(bpy, obj, source_obj=source_obj)
    scene = bpy.context.scene
    previous_engine = getattr(scene.render, "engine", None)
    try:
        scene.render.engine = "CYCLES"
        kwargs = {"type": bake_type, "margin": int(margin)}
        if source_obj is not None:
            kwargs["use_selected_to_active"] = True
        bpy.ops.object.bake(**kwargs)
        _save_bake_image(image, path)
    finally:
        if previous_engine is not None:
            scene.render.engine = previous_engine
    return info


def _map_output_path(output_dir: Path, object_name: str, map_name: str) -> Path:
    safe_object = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in object_name).strip("_") or "object"
    return output_dir / f"{safe_object}_{map_name}.png"


def save_material_preset(material_name: str, preset_name: str, include_nodes: bool = True) -> dict:
    """Save one material into a scene-local portable preset."""
    try:
        import bpy

        material = _material_named(bpy, material_name)
        if material is None:
            return skill_error(f"Material not found: {material_name}", f"No material named '{material_name}'.")
        presets = _preset_store(bpy.context.scene)
        preset = _make_material_preset(material, preset_name, include_nodes)
        presets[preset_name] = preset
        _save_preset_store(bpy.context.scene, presets)
        return skill_success("Material preset saved", preset=preset, preset_count=len(presets))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to save material preset {preset_name}")


def list_material_presets() -> dict:
    """List scene-local material presets."""
    try:
        import bpy

        presets = _preset_store(bpy.context.scene)
        items = [
            {
                "preset_name": name,
                "source_material": preset.get("source_material"),
                "schema": preset.get("schema"),
                "created_at": preset.get("created_at"),
                "include_nodes": bool(preset.get("include_nodes")),
            }
            for name, preset in sorted(presets.items())
        ]
        return skill_success("Material presets listed", presets=items, count=len(items), schema=MATERIAL_PRESET_SCHEMA)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list material presets")


def load_material_preset(preset_name: str, target_object: Optional[str] = None) -> dict:
    """Load a scene-local material preset and optionally assign it to an object."""
    try:
        import bpy

        presets = _preset_store(bpy.context.scene)
        preset = presets.get(preset_name)
        if preset is None:
            return skill_error(f"Material preset not found: {preset_name}", "Save a preset before loading it.")
        material_name = str(preset.get("material", {}).get("name") or preset_name)
        material = _material_named(bpy, material_name) or bpy.data.materials.new(material_name)
        summary = _apply_material_preset(material, preset)
        assigned = False
        if target_object:
            obj = _object_named(bpy, target_object)
            if obj is None:
                return skill_error(f"Object not found: {target_object}", f"No object named '{target_object}'.")
            if getattr(obj, "type", None) != "MESH":
                return skill_error(f"{target_object} is not a mesh", "Material presets can only be assigned to meshes.")
            _assign_material_to_object(obj, material)
            assigned = True
        return skill_success(
            "Material preset loaded",
            preset_name=preset_name,
            material=summary,
            target_object=target_object,
            assigned=assigned,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to load material preset {preset_name}")


def delete_material_preset(preset_name: str) -> dict:
    """Delete a scene-local material preset."""
    try:
        import bpy

        presets = _preset_store(bpy.context.scene)
        if preset_name not in presets:
            return skill_error(f"Material preset not found: {preset_name}", "No preset with that name exists.")
        removed = presets.pop(preset_name)
        _save_preset_store(bpy.context.scene, presets)
        return skill_success(
            "Material preset deleted", preset_name=preset_name, removed=removed, preset_count=len(presets)
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to delete material preset {preset_name}")


def get_shader_assignment(object_name: str) -> dict:
    """Return material slot assignment for one object."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        assignments = _material_slot_assignments(obj)
        return skill_success(
            "Shader assignment retrieved",
            object_name=object_name,
            assignments=assignments,
            count=len(assignments),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to get shader assignment for {object_name}")


def get_material_connections(material_name: str) -> dict:
    """Return material node and link connectivity."""
    try:
        import bpy

        material = _material_named(bpy, material_name)
        if material is None:
            return skill_error(f"Material not found: {material_name}", f"No material named '{material_name}'.")
        if not getattr(material, "use_nodes", False) or getattr(material, "node_tree", None) is None:
            return skill_error(f"Material {material_name} does not use nodes", "Enable material nodes first.")
        nodes = [_node_info(node) for node in _iter_collection(material.node_tree.nodes)]
        links = [_link_info(link) for link in _iter_collection(material.node_tree.links)]
        return skill_success(
            "Material connections retrieved",
            material_name=material_name,
            nodes=nodes,
            links=links,
            node_count=len(nodes),
            link_count=len(links),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to get material connections for {material_name}")


def set_material_attribute(material_name: str, attribute: str, value: Any) -> dict:
    """Set a material attribute or Principled BSDF input."""
    try:
        import bpy

        material = _material_named(bpy, material_name)
        if material is None:
            return skill_error(f"Material not found: {material_name}", f"No material named '{material_name}'.")
        key = attribute.strip().lower().replace("-", "_").replace(" ", "_")
        principled_inputs = {
            "base_color": "Base Color",
            "color": "Base Color",
            "metallic": "Metallic",
            "roughness": "Roughness",
            "alpha": "Alpha",
            "emission_color": "Emission Color",
            "emission_strength": "Emission Strength",
        }
        if key in principled_inputs:
            node_tree = _ensure_material_nodes(material)
            node = _find_principled_node(node_tree.nodes)
            if node is None:
                return skill_error(f"No Principled BSDF node in {material_name}", "Create a Principled node first.")
            socket_name = principled_inputs[key]
            socket = _get_socket(node.inputs, socket_name)
            if socket is None:
                return skill_error(f"Input not found: {socket_name}", "The material has no matching Principled input.")
            updated = _set_socket_value(socket, value)
            if socket_name == "Base Color":
                try:
                    material.diffuse_color = updated
                except Exception:
                    pass
            return skill_success(
                "Material attribute set",
                material_name=material_name,
                attribute=attribute,
                target="principled_input",
                socket=socket_name,
                value=updated,
            )
        if key in {"diffuse_color", "blend_method", "use_nodes"}:
            setattr(material, key, value)
            return skill_success(
                "Material attribute set",
                material_name=material_name,
                attribute=attribute,
                target="material",
                value=_jsonable(getattr(material, key, value)),
            )
        return skill_error("Unsupported material attribute", f"Unsupported attribute: {attribute}")
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set material attribute {attribute}")


def assign_texture(material_name: str, image_path: str, target_socket: str = "Base Color") -> dict:
    """Assign an image texture file to a material socket."""
    return assign_texture_node(material_name, image_path, target_socket)


def list_images() -> dict:
    """List loaded Blender images."""
    try:
        import bpy

        images = [_image_info(image) for image in _iter_collection(bpy.data.images)]
        return skill_success("Images listed", images=images, count=len(images))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list images")


def reload_image(image_name: str) -> dict:
    """Reload one loaded image from disk."""
    try:
        import bpy

        image = _image_named(bpy, image_name)
        if image is None:
            return skill_error(f"Image not found: {image_name}", f"No image named '{image_name}'.")
        reloader = getattr(image, "reload", None)
        if callable(reloader):
            reloader()
        return skill_success("Image reloaded", image=_image_info(image))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to reload image {image_name}")


def list_color_spaces() -> dict:
    """List common color-management options and current scene settings."""
    try:
        import bpy

        view_settings = getattr(bpy.context.scene, "view_settings", None)
        return skill_success(
            "Color management options listed",
            current=_view_settings_info(view_settings) if view_settings is not None else {},
            view_transforms=["AgX", "Filmic", "Standard", "Raw"],
            looks=["None", "Medium High Contrast", "High Contrast", "Medium Low Contrast"],
            image_color_spaces=["sRGB", "Linear", "Non-Color", "Raw"],
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list color spaces")


def set_color_management(
    view_transform: Optional[str] = None,
    look: Optional[str] = None,
    exposure: Optional[float] = None,
    gamma: Optional[float] = None,
) -> dict:
    """Set current scene color-management view settings."""
    try:
        import bpy

        view_settings = getattr(bpy.context.scene, "view_settings", None)
        if view_settings is None:
            return skill_error("Color management unavailable", "Scene view_settings is not available.")
        if view_transform is not None:
            view_settings.view_transform = view_transform
        if look is not None:
            view_settings.look = look
        if exposure is not None:
            view_settings.exposure = float(exposure)
        if gamma is not None:
            view_settings.gamma = float(gamma)
        return skill_success("Color management updated", current=_view_settings_info(view_settings))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set color management")


def list_bake_targets(object_name: Optional[str] = None) -> dict:
    """List mesh objects that can be texture-baked."""
    try:
        import bpy

        objects = [_object_named(bpy, object_name)] if object_name else list(_iter_collection(bpy.data.objects))
        targets = []
        for obj in objects:
            if obj is None:
                continue
            if getattr(obj, "type", None) == "MESH":
                targets.append(_bake_target_info(obj))
        if object_name and not targets:
            return skill_error(f"Bake target not found: {object_name}", "No mesh bake target matched that name.")
        return skill_success("Bake targets listed", targets=targets, count=len(targets))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list bake targets")


def bake_textures(
    object_name: str,
    maps: List[str],
    output_dir: str,
    resolution: int = 512,
    margin: int = 16,
    dry_run: bool = False,
) -> dict:
    """Bake one or more texture maps to a local output directory."""
    try:
        import bpy

        obj, error = _ensure_mesh_object(bpy, object_name)
        if error:
            return error
        output_path, error = _safe_output_dir(output_dir)
        if error or output_path is None:
            return error
        map_names, unsupported = _normalise_maps(maps or [])
        if unsupported or not map_names:
            return skill_error(
                "Unsupported bake map",
                f"Unsupported maps: {', '.join(unsupported or maps or [])}",
                supported_maps=sorted(SUPPORTED_BAKE_MAPS),
            )
        warnings = []
        data = getattr(obj, "data", None)
        if not _iter_collection(getattr(data, "uv_layers", [])):
            warnings.append("Object has no UV layers; Blender may generate incomplete bake results.")
        planned = [_map_output_path(output_path, object_name, map_name) for map_name in map_names]
        outputs = [
            _bake_one_map(bpy, obj, map_name, path, int(resolution), int(margin), dry_run)
            for map_name, path in zip(map_names, planned)
        ]
        written_files = [] if dry_run else [item["path"] for item in outputs]
        return skill_success(
            "Texture bake completed" if not dry_run else "Texture bake dry run completed",
            object_name=object_name,
            map_names=map_names,
            written_files=written_files,
            planned_files=[item["path"] for item in outputs],
            warnings=warnings,
            bake_settings={"resolution": int(resolution), "margin": int(margin), "dry_run": bool(dry_run)},
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to bake textures for {object_name}")


def bake_ambient_occlusion(object_name: str, output_path: str, settings: Optional[Dict[str, Any]] = None) -> dict:
    """Bake ambient occlusion to one explicit file path."""
    return _bake_explicit_map(object_name, "ambient_occlusion", output_path, settings)


def bake_lighting(object_name: str, output_path: str, settings: Optional[Dict[str, Any]] = None) -> dict:
    """Bake lighting/combined contribution to one explicit file path."""
    return _bake_explicit_map(object_name, "lighting", output_path, settings)


def _bake_explicit_map(object_name: str, map_name: str, output_path: str, settings: Optional[Dict[str, Any]]) -> dict:
    settings = settings or {}
    try:
        import bpy

        obj, error = _ensure_mesh_object(bpy, object_name)
        if error:
            return error
        path, error = _safe_output_path(output_path)
        if error or path is None:
            return error
        resolution = int(settings.get("resolution", 512))
        margin = int(settings.get("margin", 16))
        dry_run = bool(settings.get("dry_run", False))
        output = _bake_one_map(bpy, obj, map_name, path, resolution, margin, dry_run)
        return skill_success(
            f"{map_name.replace('_', ' ').title()} bake completed"
            if not dry_run
            else f"{map_name} bake dry run completed",
            object_name=object_name,
            map_name=map_name,
            written_files=[] if dry_run else [output["path"]],
            planned_files=[output["path"]],
            bake_settings={"resolution": resolution, "margin": margin, "dry_run": dry_run},
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to bake {map_name} for {object_name}")


def transfer_maps(
    source_object: str,
    target_object: str,
    output_dir: str,
    maps: Optional[List[str]] = None,
    resolution: int = 512,
    margin: int = 16,
    dry_run: bool = False,
) -> dict:
    """Bake selected-to-active transfer maps from one mesh to another."""
    try:
        import bpy

        source, error = _ensure_mesh_object(bpy, source_object)
        if error:
            return error
        target, error = _ensure_mesh_object(bpy, target_object)
        if error:
            return error
        output_path, error = _safe_output_dir(output_dir)
        if error or output_path is None:
            return error
        map_names, unsupported = _normalise_maps(maps or ["normal"])
        if unsupported:
            return skill_error(
                "Unsupported transfer map",
                f"Unsupported maps: {', '.join(unsupported)}",
                supported_maps=sorted(SUPPORTED_BAKE_MAPS),
            )
        planned = [output_path / f"{source_object}_to_{target_object}_{map_name}.png" for map_name in map_names]
        outputs = [
            _bake_one_map(bpy, target, map_name, path, int(resolution), int(margin), dry_run, source_obj=source)
            for map_name, path in zip(map_names, planned)
        ]
        return skill_success(
            "Transfer maps completed" if not dry_run else "Transfer maps dry run completed",
            source_object=source_object,
            target_object=target_object,
            map_names=map_names,
            written_files=[] if dry_run else [item["path"] for item in outputs],
            planned_files=[item["path"] for item in outputs],
            warnings=["Transfer maps use Blender selected-to-active baking; verify cages for production assets."],
            bake_settings={"resolution": int(resolution), "margin": int(margin), "dry_run": bool(dry_run)},
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to transfer maps from {source_object} to {target_object}")
