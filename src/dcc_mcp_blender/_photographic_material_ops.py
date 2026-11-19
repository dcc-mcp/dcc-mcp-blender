"""Photographic toy-material and edge-finish setup for Blender."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

MATERIAL_KINDS = ("PAINTED_TOY", "GLOSS_BLACK_EYE", "PLANT_LEAF")
PBR_MAPS = ("diffuse", "roughness", "normal")
PREFIX = "DCC Photo "
TEXTURE_SOURCE_KEY = "dcc_mcp_photographic_texture_source"
NORMAL_MAP_CONVENTION_KEY = "dcc_mcp_photographic_normal_map_convention"
NORMAL_MAP_CONVENTION = "OPENGL"
BEVEL_WIDTH_MIN_MM = 0.3
BEVEL_WIDTH_MAX_MM = 0.7
BEVEL_SEGMENTS = 3


def _normalise_kind(value: str) -> str:
    kind = str(value or "PAINTED_TOY").strip().upper()
    if kind not in MATERIAL_KINDS:
        raise ValueError("material_kind must be PAINTED_TOY, GLOSS_BLACK_EYE, or PLANT_LEAF")
    return kind


def _normalise_normal_map_convention(value: Any) -> str:
    convention = str(value or "").strip().upper()
    if convention not in {"OPENGL", "GL"}:
        raise ValueError("normal_map_convention must be OPENGL for the photographic contract")
    return NORMAL_MAP_CONVENTION


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _color(value: Any, label: str) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
        raise ValueError(f"{label} must contain three or four color channels")
    channels = [_finite(component, f"{label}[{index}]") for index, component in enumerate(value)]
    if any(channel < 0.0 or channel > 1.0 for channel in channels):
        raise ValueError(f"{label} channels must be between 0 and 1")
    return channels if len(channels) == 4 else [*channels, 1.0]


def _material(bpy: Any, name: str) -> Any:
    return bpy.data.materials.get(name)


def _remove_custom_property(owner: Any, key: str) -> None:
    pop = getattr(owner, "pop", None)
    if callable(pop):
        try:
            pop(key, None)
            return
        except (TypeError, KeyError, RuntimeError):
            pass
    try:
        del owner[key]
    except (KeyError, TypeError, AttributeError, RuntimeError):
        pass


def _object(bpy: Any, name: str) -> Any:
    return bpy.data.objects.get(name)


def _socket(sockets: Any, names: tuple[str, ...]) -> Any | None:
    for name in names:
        getter = getattr(sockets, "get", None)
        candidate = getter(name) if callable(getter) else None
        if candidate is not None:
            return candidate
        for item in sockets:
            if getattr(item, "name", None) == name:
                return item
    return None


def _set_input(node: Any, names: tuple[str, ...], value: Any) -> str | None:
    target = _socket(node.inputs, names)
    if target is None:
        return None
    target.default_value = value
    return str(getattr(target, "name", names[0]))


def _node(nodes: Any, name: str, node_type: str | None = None) -> Any | None:
    getter = getattr(nodes, "get", None)
    candidate = getter(name) if callable(getter) else None
    if candidate is not None and (node_type is None or getattr(candidate, "type", None) == node_type):
        return candidate
    for candidate in nodes:
        if getattr(candidate, "name", None) == name and (
            node_type is None or getattr(candidate, "type", None) == node_type
        ):
            return candidate
    return None


def _new_node(nodes: Any, node_type: str, name: str) -> Any:
    try:
        node = nodes.new(type=node_type)
    except TypeError:
        node = nodes.new(node_type)
    node.name = name
    node.label = name
    return node


def _remove_owned_nodes(node_tree: Any) -> None:
    for node in list(node_tree.nodes):
        if str(getattr(node, "name", "")).startswith(PREFIX):
            node_tree.nodes.remove(node)


def _connect(node_tree: Any, output: Any, target: Any) -> None:
    for link in list(getattr(target, "links", ())):
        node_tree.links.remove(link)
    node_tree.links.new(output, target)


def _path_map(texture_paths: Mapping[str, Any] | None) -> dict[str, Path]:
    if texture_paths is None:
        return {}
    if not isinstance(texture_paths, Mapping):
        raise ValueError("texture_paths must be an object with diffuse, roughness, or normal paths")
    unknown = set(texture_paths) - set(PBR_MAPS)
    if unknown:
        raise ValueError(f"Unsupported texture map(s): {', '.join(sorted(str(item) for item in unknown))}")
    result = {}
    for map_name, raw_path in texture_paths.items():
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"texture_paths.{map_name} must be a local file path")
        if "://" in raw_path or raw_path.startswith("\\\\"):
            raise ValueError(f"texture_paths.{map_name} must be a local filesystem path")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"texture_paths.{map_name} does not exist: {path}")
        result[str(map_name)] = path
    return result


def _load_image(bpy: Any, path: Path, colorspace: str) -> Any:
    image = bpy.data.images.load(str(path), check_existing=True)
    settings = getattr(image, "colorspace_settings", None)
    if settings is not None:
        try:
            settings.name = colorspace
        except (TypeError, ValueError):
            pass
    return image


def _set_surface_alpha(material: Any) -> dict[str, Any]:
    if hasattr(material, "surface_render_method"):
        try:
            material.surface_render_method = "DITHERED"
            return {"property": "surface_render_method", "value": "DITHERED"}
        except (TypeError, ValueError):
            pass
    if hasattr(material, "blend_method"):
        material.blend_method = "HASHED"
        return {"property": "blend_method", "value": "HASHED"}
    return {"property": None, "value": None}


def _find_principled(node_tree: Any) -> Any | None:
    for node in node_tree.nodes:
        if getattr(node, "type", None) == "BSDF_PRINCIPLED":
            return node
    return None


def _principled(node_tree: Any) -> Any:
    return _find_principled(node_tree) or _new_node(node_tree.nodes, "ShaderNodeBsdfPrincipled", "Principled BSDF")


def _material_output(node_tree: Any) -> Any:
    for node in node_tree.nodes:
        if getattr(node, "type", None) == "OUTPUT_MATERIAL":
            return node
    return _new_node(node_tree.nodes, "ShaderNodeOutputMaterial", "Material Output")


def _configure_pbr_nodes(bpy: Any, material: Any, principled: Any, texture_paths: dict[str, Path]) -> dict[str, Any]:
    node_tree = material.node_tree
    loaded = {}
    if not texture_paths:
        return loaded
    texcoord = _new_node(node_tree.nodes, "ShaderNodeTexCoord", f"{PREFIX}Object Coordinates")
    for map_name, path in texture_paths.items():
        texture = _new_node(node_tree.nodes, "ShaderNodeTexImage", f"{PREFIX}{map_name.title()} Texture")
        texture.image = _load_image(bpy, path, "sRGB" if map_name == "diffuse" else "Non-Color")
        texture.projection = "BOX"
        texture.projection_blend = 0.25
        vector_socket = _socket(texture.inputs, ("Vector",))
        object_socket = _socket(texcoord.outputs, ("Object",))
        if vector_socket is not None and object_socket is not None:
            node_tree.links.new(object_socket, vector_socket)
        loaded[map_name] = {
            "node": texture.name,
            "path": str(path),
            "projection": getattr(texture, "projection", None),
            "projection_blend": getattr(texture, "projection_blend", None),
        }
        if map_name == "diffuse":
            output = _socket(texture.outputs, ("Color",))
            target = _socket(principled.inputs, ("Base Color",))
        elif map_name == "roughness":
            output = _socket(texture.outputs, ("Color",))
            target = _socket(principled.inputs, ("Roughness",))
        else:
            normal_map = _new_node(node_tree.nodes, "ShaderNodeNormalMap", f"{PREFIX}Normal Map")
            normal_map.inputs["Strength"].default_value = 1.0
            image_output = _socket(texture.outputs, ("Color",))
            normal_input = _socket(normal_map.inputs, ("Color",))
            if image_output is not None and normal_input is not None:
                node_tree.links.new(image_output, normal_input)
            output = _socket(normal_map.outputs, ("Normal",))
            target = _socket(principled.inputs, ("Normal",))
        if output is not None and target is not None:
            _connect(node_tree, output, target)
    return loaded


def _pbr_texture_nodes(node_tree: Any) -> dict[str, Any | None]:
    return {
        map_name: _node(node_tree.nodes, f"{PREFIX}{map_name.title()} Texture", "TEX_IMAGE") for map_name in PBR_MAPS
    }


def _uses_object_coordinates(texture: Any) -> bool:
    vector = _socket(getattr(texture, "inputs", ()), ("Vector",))
    if vector is None:
        return False
    return any(
        getattr(getattr(link, "from_node", None), "type", None) == "TEX_COORD"
        and getattr(getattr(link, "from_socket", None), "name", None) == "Object"
        for link in getattr(vector, "links", ())
    )


def _pbr_link_state(node_tree: Any) -> dict[str, bool]:
    principled = _find_principled(node_tree) if node_tree is not None else None
    nodes = _pbr_texture_nodes(node_tree) if node_tree is not None else {map_name: None for map_name in PBR_MAPS}
    normal_map = _node(node_tree.nodes, f"{PREFIX}Normal Map", "NORMAL_MAP") if node_tree is not None else None
    normal_texture = nodes.get("normal")
    principled_normal = _socket(getattr(principled, "inputs", ()), ("Normal",))
    normal_map_input = _socket(getattr(normal_map, "inputs", ()), ("Color",))
    normal_map_output = _socket(getattr(normal_map, "outputs", ()), ("Normal",))
    normal_texture_linked = _linked_from(normal_map_input, normal_texture, "Color")
    normal_linked_directly = _linked_from(principled_normal, normal_map, "Normal")
    normal_linked_through_bump = False
    if node_tree is not None and normal_map_output is not None:
        for node in node_tree.nodes:
            if getattr(node, "type", None) != "BUMP":
                continue
            bump_input = _socket(getattr(node, "inputs", ()), ("Normal",))
            if _linked_from(bump_input, normal_map, "Normal") and _linked_from(principled_normal, node, "Normal"):
                normal_linked_through_bump = True
                break
    return {
        "diffuse": _linked_from(
            _socket(getattr(principled, "inputs", ()), ("Base Color",)),
            nodes.get("diffuse"),
            "Color",
        ),
        "roughness": _linked_from(
            _socket(getattr(principled, "inputs", ()), ("Roughness",)),
            nodes.get("roughness"),
            "Color",
        ),
        "normal": normal_texture_linked and (normal_linked_directly or normal_linked_through_bump),
    }


def _image_has_alpha(image: Any) -> bool:
    if image is None:
        return False
    filepath = getattr(image, "filepath", None) or getattr(image, "filepath_raw", None)
    if filepath:
        try:
            header = Path(str(filepath)).expanduser().read_bytes()[:29]
        except OSError:
            header = b""
        if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 26:
            return header[25] in {4, 6}
        if header.startswith(b"\xff\xd8\xff"):
            return False
    channels = getattr(image, "channels", None)
    return isinstance(channels, int) and not isinstance(channels, bool) and channels >= 4


def _validate_leaf_diffuse_alpha(bpy: Any, path: Path) -> None:
    image = _load_image(bpy, path, "sRGB")
    if not _image_has_alpha(image):
        raise ValueError("PLANT_LEAF requires a diffuse scan with an alpha channel")


def _custom_value(owner: Any, key: str, default: Any = None) -> Any:
    getter = getattr(owner, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except (TypeError, ValueError, RuntimeError):
            pass
    return getattr(owner, key, default)


def _is_polyhaven_source(value: Any) -> bool:
    normalized = "".join(str(value or "").casefold().split())
    if normalized == "polyhaven":
        return True
    raw_value = str(value or "").strip()
    parsed = urlparse(raw_value if "://" in raw_value else f"//{raw_value}")
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    return hostname == "polyhaven.com" or hostname.endswith(".polyhaven.com")


def _linked_from(target: Any, source: Any, source_socket_name: str) -> bool:
    if target is None or source is None:
        return False

    def same_node(left: Any, right: Any) -> bool:
        if left is right:
            return True
        left_pointer = getattr(left, "as_pointer", None)
        right_pointer = getattr(right, "as_pointer", None)
        if callable(left_pointer) and callable(right_pointer):
            try:
                return int(left_pointer()) == int(right_pointer())
            except (TypeError, ValueError, RuntimeError):
                pass
        try:
            return left == right
        except (TypeError, ValueError, RuntimeError):
            return False

    return any(
        same_node(getattr(link, "from_node", None), source)
        and getattr(getattr(link, "from_socket", None), "name", None) == source_socket_name
        for link in getattr(target, "links", ())
    )


def _configure_noise_bump(material: Any, principled: Any) -> dict[str, float]:
    node_tree = material.node_tree
    noise = _new_node(node_tree.nodes, "ShaderNodeTexNoise", f"{PREFIX}Fine Surface Noise")
    _set_input(noise, ("Scale",), 900.0)
    _set_input(noise, ("Detail",), 2.0)
    bump = _new_node(node_tree.nodes, "ShaderNodeBump", f"{PREFIX}Fine Surface Bump")
    _set_input(bump, ("Strength",), 0.03)
    _set_input(bump, ("Distance",), 0.0002)
    noise_output = _socket(noise.outputs, ("Fac",))
    height_input = _socket(bump.inputs, ("Height",))
    if noise_output is not None and height_input is not None:
        node_tree.links.new(noise_output, height_input)
    existing_normal = _socket(bump.inputs, ("Normal",))
    principled_normal = _socket(principled.inputs, ("Normal",))
    if existing_normal is not None and principled_normal is not None:
        normal_map = _node(node_tree.nodes, f"{PREFIX}Normal Map")
        normal_output = _socket(normal_map.outputs, ("Normal",)) if normal_map is not None else None
        if normal_output is not None:
            for link in list(getattr(existing_normal, "links", ())):
                node_tree.links.remove(link)
            node_tree.links.new(normal_output, existing_normal)
        for link in list(getattr(principled_normal, "links", ())):
            node_tree.links.remove(link)
        node_tree.links.new(_socket(bump.outputs, ("Normal",)), principled_normal)
    return {"scale": 900.0, "strength": 0.03, "distance_m": 0.0002}


def _configure_material_nodes(
    bpy: Any,
    material: Any,
    kind: str,
    base_color: list[float],
    texture_paths: dict[str, Path],
    alpha_threshold: float,
) -> dict[str, Any]:
    material.use_nodes = True
    node_tree = material.node_tree
    _remove_owned_nodes(node_tree)
    principled = _principled(node_tree)
    output = _material_output(node_tree)
    _connect(node_tree, _socket(principled.outputs, ("BSDF",)), _socket(output.inputs, ("Surface",)))
    _set_input(principled, ("Base Color",), base_color)
    _set_input(principled, ("Metallic",), 0.0)
    _set_input(principled, ("Alpha",), 1.0)
    _set_input(principled, ("Roughness",), 0.48)
    _set_input(principled, ("Coat Weight", "Coat"), 0.25)
    _set_input(principled, ("Coat Roughness",), 0.3)
    surface_alpha = _set_surface_alpha(material) if kind == "PLANT_LEAF" else None

    if kind == "PAINTED_TOY":
        bump = None
    elif kind == "GLOSS_BLACK_EYE":
        _set_input(principled, ("Base Color",), [0.002, 0.002, 0.002, 1.0])
        _set_input(principled, ("Roughness",), 0.08)
        _set_input(principled, ("Coat Weight", "Coat"), 1.0)
        _set_input(principled, ("Coat Roughness",), 0.03)
        bump = None
    else:
        _set_input(principled, ("Roughness",), 0.48)
        _set_input(principled, ("Coat Weight", "Coat"), 0.0)
        _set_input(principled, ("Subsurface Weight", "Subsurface"), 0.12)
        _set_input(principled, ("Transmission Weight", "Transmission"), 0.04)
        bump = None

    loaded = _configure_pbr_nodes(bpy, material, principled, texture_paths)
    if kind == "PAINTED_TOY":
        bump = _configure_noise_bump(material, principled)
    alpha_node = None
    if kind == "PLANT_LEAF" and "diffuse" in texture_paths:
        diffuse = _node(node_tree.nodes, f"{PREFIX}Diffuse Texture")
        alpha_node = _new_node(node_tree.nodes, "ShaderNodeMath", f"{PREFIX}Leaf Alpha Cutout")
        alpha_node.operation = "GREATER_THAN"
        _set_input(alpha_node, ("Value",), alpha_threshold)
        alpha_output = _socket(diffuse.outputs, ("Alpha",)) if diffuse is not None else None
        alpha_input = _socket(alpha_node.inputs, ("Value",))
        threshold_input = _socket(alpha_node.inputs, ("Value_001", "Value 1"))
        principled_alpha = _socket(principled.inputs, ("Alpha",))
        if (
            alpha_output is not None
            and alpha_input is not None
            and threshold_input is not None
            and principled_alpha is not None
        ):
            threshold_input.default_value = alpha_threshold
            node_tree.links.new(alpha_output, alpha_input)
            _connect(node_tree, _socket(alpha_node.outputs, ("Value",)), principled_alpha)

    material.diffuse_color = base_color
    material["dcc_mcp_photographic_material"] = "v1"
    material["dcc_mcp_photographic_material_kind"] = kind
    material["dcc_mcp_photographic_texture_maps"] = ",".join(sorted(loaded))
    return {
        "kind": kind,
        "base_color": list(base_color),
        "texture_maps": loaded,
        "noise_bump": bump,
        "leaf_alpha_cutout": alpha_node is not None,
        "surface_alpha": surface_alpha,
    }


def configure_photographic_material(
    material_name: str,
    material_kind: str = "PAINTED_TOY",
    base_color: Any = (0.22, 0.38, 0.78, 1.0),
    texture_paths: Mapping[str, Any] | None = None,
    target_object: str | None = None,
    alpha_threshold: float = 0.5,
    texture_source: str | None = None,
    normal_map_convention: str = NORMAL_MAP_CONVENTION,
) -> dict:
    """Create or update a toy material with photographic surface behavior."""
    try:
        kind = _normalise_kind(material_kind)
        color = _color(base_color, "base_color")
        threshold = _finite(alpha_threshold, "alpha_threshold")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("alpha_threshold must be between 0 and 1")
        if texture_source is not None:
            if not isinstance(texture_source, str) or not texture_source.strip():
                raise ValueError("texture_source must be a non-empty string when supplied")
            source = texture_source.strip()
        else:
            source = None
        convention = _normalise_normal_map_convention(normal_map_convention)
        paths = _path_map(texture_paths)
        if kind == "PLANT_LEAF" and "diffuse" not in paths:
            raise ValueError("PLANT_LEAF requires a diffuse scan with an alpha channel")
        import bpy

        if kind == "PLANT_LEAF":
            _validate_leaf_diffuse_alpha(bpy, paths["diffuse"])
        material = _material(bpy, material_name)
        if material is None:
            material = bpy.data.materials.new(material_name)
        if target_object:
            obj = _object(bpy, target_object)
            if obj is None:
                return skill_error("Object not found", f"No object named '{target_object}' exists.")
            if getattr(obj, "type", None) != "MESH":
                return skill_error("Object is not a mesh", f"'{target_object}' cannot receive a mesh material.")
        settings = _configure_material_nodes(bpy, material, kind, color, paths, threshold)
        if target_object:
            materials = obj.data.materials
            if len(materials) == 0:
                materials.append(material)
            else:
                materials[0] = material
        if source is not None:
            material[TEXTURE_SOURCE_KEY] = source
        else:
            _remove_custom_property(material, TEXTURE_SOURCE_KEY)
        material[NORMAL_MAP_CONVENTION_KEY] = convention
        return skill_success(
            f"Photographic material configured: {material.name}",
            material_name=material.name,
            target_object=target_object,
            settings=settings,
            contract={
                "painted_roughness": 0.48,
                "painted_coat_weight": 0.25,
                "painted_coat_roughness": 0.3,
                "fine_noise_scale": 900.0,
                "fine_noise_strength": 0.03,
                "fine_noise_distance_m": 0.0002,
                "gloss_black_roughness": 0.08,
                "gloss_black_coat_weight": 1.0,
                "gloss_black_coat_roughness": 0.03,
                "box_projection_blend": 0.25,
                "texture_source": source,
                "normal_map_convention": convention,
            },
            prompt="Add a 0.3–0.7 mm, three-segment bevel to every toy edge, then validate the material.",
        )
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid photographic material request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to configure photographic material: {material_name}")


def configure_toy_bevel(
    object_name: str,
    width_mm: float = 0.5,
    segments: int = BEVEL_SEGMENTS,
    modifier_name: str = "DCC Photographic Bevel",
) -> dict:
    """Add or update a render-visible bevel that covers every mesh edge."""
    try:
        width = _finite(width_mm, "width_mm")
        if not BEVEL_WIDTH_MIN_MM <= width <= BEVEL_WIDTH_MAX_MM:
            raise ValueError("width_mm must be between 0.3 and 0.7")
        if isinstance(segments, bool) or not isinstance(segments, int) or segments != BEVEL_SEGMENTS:
            raise ValueError("segments must be exactly 3")
        import bpy

        obj = _object(bpy, object_name)
        if obj is None:
            return skill_error("Object not found", f"No object named '{object_name}' exists.")
        if getattr(obj, "type", None) != "MESH":
            return skill_error("Object is not a mesh", f"'{object_name}' cannot receive a mesh bevel.")
        modifier = obj.modifiers.get(modifier_name)
        if modifier is not None and getattr(modifier, "type", None) != "BEVEL":
            return skill_error("Modifier name collision", f"'{modifier_name}' already names a non-bevel modifier.")
        if modifier is None:
            modifier = obj.modifiers.new(modifier_name, "BEVEL")
        modifier.width = width / 1000.0
        modifier.segments = BEVEL_SEGMENTS
        modifier.limit_method = "NONE"
        if hasattr(modifier, "affect"):
            modifier.affect = "EDGES"
        if hasattr(modifier, "offset_type"):
            modifier.offset_type = "WIDTH"
        modifier.show_viewport = True
        modifier.show_render = True
        return skill_success(
            f"Photographic bevel configured: {object_name}",
            object_name=object_name,
            modifier_name=modifier.name,
            bevel={
                "width_mm": width,
                "width_m": modifier.width,
                "segments": modifier.segments,
                "limit_method": modifier.limit_method,
                "offset_type": getattr(modifier, "offset_type", None),
                "affect": getattr(modifier, "affect", None),
                "show_render": bool(modifier.show_render),
            },
        )
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid photographic bevel request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to configure photographic bevel: {object_name}")


def _socket_value(node: Any, names: tuple[str, ...]) -> Any:
    socket = _socket(node.inputs, names)
    return getattr(socket, "default_value", None) if socket is not None else None


def _close(actual: Any, expected: float, tolerance: float = 1e-5) -> bool:
    try:
        return math.isclose(float(actual), expected, abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def validate_photographic_material(
    material_name: str,
    material_kind: str = "PAINTED_TOY",
    object_name: str | None = None,
    require_pbr_textures: bool = True,
    bevel_width_mm: float = 0.5,
) -> dict:
    """Read-only validation for toy material nodes and the edge bevel contract."""
    try:
        kind = _normalise_kind(material_kind)
        expected_width = _finite(bevel_width_mm, "bevel_width_mm")
        import bpy

        material = _material(bpy, material_name)
        if material is None:
            return skill_error("Material not found", f"No material named '{material_name}' exists.")
        issues = []

        def issue(code: str, field: str, expected: Any, actual: Any, message: str) -> None:
            issues.append(
                {
                    "code": code,
                    "severity": "error",
                    "field": field,
                    "expected": expected,
                    "actual": actual,
                    "message": message,
                }
            )

        if not getattr(material, "use_nodes", False) or getattr(material, "node_tree", None) is None:
            issue("MATERIAL_NODES_DISABLED", "use_nodes", True, False, "Use a node-based material.")
            return skill_success(
                "Photographic material validation completed",
                valid=False,
                material_name=material_name,
                material_kind=kind,
                issues=issues,
            )
        principled = _find_principled(material.node_tree)
        if principled is None:
            issue("PRINCIPLED_NODE_MISSING", "principled", True, False, "A Principled BSDF node is required.")
        else:
            if kind == "PAINTED_TOY":
                if not _close(_socket_value(principled, ("Roughness",)), 0.48):
                    issue(
                        "PAINTED_ROUGHNESS_MISMATCH",
                        "Roughness",
                        0.48,
                        _socket_value(principled, ("Roughness",)),
                        "Painted toys use roughness 0.48.",
                    )
                if not _close(_socket_value(principled, ("Coat Weight", "Coat")), 0.25):
                    issue(
                        "PAINTED_COAT_MISMATCH",
                        "Coat Weight",
                        0.25,
                        _socket_value(principled, ("Coat Weight", "Coat")),
                        "Painted toys use coat weight 0.25.",
                    )
                noise = _node(material.node_tree.nodes, f"{PREFIX}Fine Surface Noise")
                bump = _node(material.node_tree.nodes, f"{PREFIX}Fine Surface Bump")
                if noise is None or not _close(_socket_value(noise, ("Scale",)), 900.0):
                    issue(
                        "FINE_NOISE_MISSING",
                        "fine_noise_scale",
                        900.0,
                        None,
                        "Painted toys need the fine scale 900 noise bump.",
                    )
                if (
                    bump is None
                    or not _close(_socket_value(bump, ("Strength",)), 0.03)
                    or not _close(_socket_value(bump, ("Distance",)), 0.0002, 1e-7)
                ):
                    issue(
                        "FINE_BUMP_MISMATCH",
                        "fine_bump",
                        {"strength": 0.03, "distance_m": 0.0002},
                        None,
                        "Painted toys need a 0.03 strength, 0.2 mm bump.",
                    )
            elif kind == "GLOSS_BLACK_EYE":
                if not _close(_socket_value(principled, ("Roughness",)), 0.08):
                    issue(
                        "EYE_ROUGHNESS_MISMATCH",
                        "Roughness",
                        0.08,
                        _socket_value(principled, ("Roughness",)),
                        "Gloss-black eyes use roughness 0.08.",
                    )
                if not _close(_socket_value(principled, ("Coat Weight", "Coat")), 1.0):
                    issue(
                        "EYE_COAT_MISMATCH",
                        "Coat Weight",
                        1.0,
                        _socket_value(principled, ("Coat Weight", "Coat")),
                        "Gloss-black eyes use coat weight 1.0.",
                    )
                if not _close(_socket_value(principled, ("Coat Roughness",)), 0.03):
                    issue(
                        "EYE_COAT_ROUGHNESS_MISMATCH",
                        "Coat Roughness",
                        0.03,
                        _socket_value(principled, ("Coat Roughness",)),
                        "Gloss-black eyes use coat roughness 0.03.",
                    )
            else:
                if not _close(_socket_value(principled, ("Subsurface Weight", "Subsurface")), 0.12):
                    issue(
                        "LEAF_SUBSURFACE_MISSING",
                        "Subsurface Weight",
                        0.12,
                        _socket_value(principled, ("Subsurface Weight", "Subsurface")),
                        "Plant leaves need a little translucency.",
                    )
                if not getattr(material, "surface_render_method", None) and not getattr(material, "blend_method", None):
                    issue(
                        "LEAF_ALPHA_MODE_MISSING",
                        "surface_render_method",
                        "DITHERED or HASHED",
                        None,
                        "Plant leaves need an alpha-capable surface mode.",
                    )

        texture_nodes = [
            node
            for node in material.node_tree.nodes
            if str(getattr(node, "name", "")).startswith(PREFIX) and getattr(node, "type", None) == "TEX_IMAGE"
        ]
        pbr_nodes = _pbr_texture_nodes(material.node_tree)
        if require_pbr_textures and any(pbr_nodes[map_name] is None for map_name in PBR_MAPS):
            missing_maps = [map_name for map_name in PBR_MAPS if pbr_nodes[map_name] is None]
            issue(
                "PBR_TEXTURES_INCOMPLETE",
                "texture_maps",
                PBR_MAPS,
                missing_maps,
                "Diffuse, roughness, and GL normal maps are required.",
            )
        texture_source = _custom_value(material, TEXTURE_SOURCE_KEY)
        if require_pbr_textures and not _is_polyhaven_source(texture_source):
            issue(
                "PBR_TEXTURE_SOURCE_MISMATCH",
                "texture_source",
                "Poly Haven",
                texture_source,
                "Photographic PBR maps must carry a Poly Haven provenance label.",
            )
        normal_map_convention = _custom_value(material, NORMAL_MAP_CONVENTION_KEY)
        if require_pbr_textures and normal_map_convention != NORMAL_MAP_CONVENTION:
            issue(
                "PBR_NORMAL_CONVENTION_MISMATCH",
                "normal_map_convention",
                NORMAL_MAP_CONVENTION,
                normal_map_convention,
                "Photographic PBR normal maps must use the OpenGL convention.",
            )
        for node in texture_nodes:
            if getattr(node, "projection", None) != "BOX" or not _close(getattr(node, "projection_blend", None), 0.25):
                issue(
                    "TEXTURE_PROJECTION_MISMATCH",
                    node.name,
                    {"projection": "BOX", "projection_blend": 0.25},
                    {
                        "projection": getattr(node, "projection", None),
                        "projection_blend": getattr(node, "projection_blend", None),
                    },
                    "PBR textures use object-space box projection with blend 0.25.",
                )
        if require_pbr_textures:
            for map_name, node in pbr_nodes.items():
                if node is None:
                    continue
                if getattr(node, "image", None) is None:
                    issue(
                        "PBR_TEXTURE_IMAGE_MISSING",
                        map_name,
                        "loaded image",
                        None,
                        "Every photographic PBR map must have a loaded image.",
                    )
                if not _uses_object_coordinates(node):
                    issue(
                        "TEXTURE_COORDINATES_MISMATCH",
                        map_name,
                        "Object coordinates",
                        False,
                        "PBR textures must use object-space coordinates.",
                    )
            links = _pbr_link_state(material.node_tree)
            for map_name, valid in links.items():
                if not valid:
                    issue(
                        "PBR_TEXTURE_LINK_MISSING",
                        map_name,
                        True,
                        False,
                        "Every photographic PBR map must be connected to the Principled BSDF.",
                    )

        if kind == "PLANT_LEAF":
            diffuse = pbr_nodes.get("diffuse")
            alpha_node = _node(material.node_tree.nodes, f"{PREFIX}Leaf Alpha Cutout", "MATH")
            alpha_input = _socket(getattr(alpha_node, "inputs", ()), ("Value",)) if alpha_node is not None else None
            principled_alpha = (
                _socket(getattr(principled, "inputs", ()), ("Alpha",)) if principled is not None else None
            )
            if (
                diffuse is None
                or alpha_node is None
                or not _linked_from(alpha_input, diffuse, "Alpha")
                or not _linked_from(principled_alpha, alpha_node, "Value")
            ):
                issue(
                    "LEAF_ALPHA_CUTOUT_MISSING",
                    "alpha_cutout",
                    True,
                    False,
                    "Plant leaves need the scanned diffuse alpha connected through a cutout node.",
                )
            elif not _image_has_alpha(getattr(diffuse, "image", None)):
                issue(
                    "LEAF_ALPHA_CHANNEL_MISSING",
                    "diffuse_alpha_channel",
                    True,
                    False,
                    "Plant leaves need a scanned diffuse image with an alpha channel.",
                )
            if principled is not None and not _close(
                _socket_value(principled, ("Transmission Weight", "Transmission")), 0.04
            ):
                issue(
                    "LEAF_TRANSMISSION_MISMATCH",
                    "Transmission Weight",
                    0.04,
                    _socket_value(principled, ("Transmission Weight", "Transmission")),
                    "Plant leaves use a small transmission contribution for translucency.",
                )

        bevel = None
        if object_name:
            obj = _object(bpy, object_name)
            if obj is None:
                issue("OBJECT_NOT_FOUND", "object_name", object_name, None, "The bevel target object does not exist.")
            elif getattr(obj, "type", None) != "MESH":
                issue(
                    "OBJECT_NOT_MESH",
                    "object_name",
                    "MESH",
                    getattr(obj, "type", None),
                    "The bevel target must be a mesh.",
                )
            else:
                bevel = next(
                    (
                        candidate
                        for candidate in obj.modifiers
                        if str(getattr(candidate, "name", "")) == "DCC Photographic Bevel"
                    ),
                    None,
                )
                if bevel is None:
                    issue(
                        "BEVEL_MISSING",
                        "modifier",
                        "DCC Photographic Bevel",
                        None,
                        "Add a three-segment bevel to every toy edge.",
                    )
                else:
                    if not _close(float(bevel.width) * 1000.0, expected_width):
                        issue(
                            "BEVEL_WIDTH_MISMATCH",
                            "bevel_width_mm",
                            expected_width,
                            float(bevel.width) * 1000.0,
                            "Use a 0.3–0.7 mm bevel on toy edges.",
                        )
                    if (
                        getattr(bevel, "segments", None) != BEVEL_SEGMENTS
                        or getattr(bevel, "limit_method", None) != "NONE"
                        or getattr(bevel, "offset_type", None) not in {"OFFSET", "WIDTH", "DEPTH", "ABSOLUTE"}
                        or getattr(bevel, "affect", "EDGES") != "EDGES"
                        or getattr(bevel, "show_render", True) is not True
                    ):
                        issue(
                            "BEVEL_CONTRACT_MISMATCH",
                            "bevel",
                            {
                                "segments": 3,
                                "limit_method": "NONE",
                                "offset_type": ["OFFSET", "WIDTH", "DEPTH", "ABSOLUTE"],
                                "affect": "EDGES",
                                "show_render": True,
                            },
                            {
                                "segments": getattr(bevel, "segments", None),
                                "limit_method": getattr(bevel, "limit_method", None),
                                "offset_type": getattr(bevel, "offset_type", None),
                                "affect": getattr(bevel, "affect", None),
                                "show_render": getattr(bevel, "show_render", None),
                            },
                            "Bevel every edge with three segments.",
                        )
        return skill_success(
            "Photographic material validation completed",
            valid=not issues,
            material_name=material_name,
            material_kind=kind,
            texture_map_count=len(texture_nodes),
            bevel={"name": getattr(bevel, "name", None), "width_mm": float(bevel.width) * 1000.0}
            if bevel is not None
            else None,
            issues=issues,
        )
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid photographic material validation request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to validate photographic material: {material_name}")
