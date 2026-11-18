"""Motivated lighting setup and validation for photographic toy shots."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._photographic_color_ops import (
    DEFAULT_HIGHLIGHT_THRESHOLD,
    DEFAULT_MAX_SAMPLES,
    DEFAULT_SATURATION_THRESHOLD,
    DEFAULT_WARM_BIAS_THRESHOLD,
    analyze_rgb_pixels,
)

SOURCE_TYPES = ("SUN_WINDOW", "LAMP", "SCREEN", "OUTDOOR_HDRI")
SOURCE_LIGHT_TYPES = {
    "SUN_WINDOW": "AREA",
    "LAMP": "POINT",
    "SCREEN": "AREA",
    "OUTDOOR_HDRI": "SUN",
}
PREFIX = "DCC Photo Light "
SUN_ANGLE_DEGREES = 1.2


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _vector(value: Any, label: str, default: tuple[float, float, float]) -> list[float]:
    if value is None:
        return list(default)
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{label} must contain exactly three finite numbers")
    return [_finite(component, f"{label}[{index}]") for index, component in enumerate(value)]


def _color(value: Any, label: str, default: tuple[float, float, float]) -> list[float]:
    values = default if value is None else value
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(f"{label} must contain three finite channels")
    result = [_finite(component, f"{label}[{index}]") for index, component in enumerate(values)]
    if any(channel < 0.0 or channel > 1.0 for channel in result):
        raise ValueError(f"{label} channels must be between 0 and 1")
    return result


def _normalise_source_type(value: str) -> str:
    source_type = str(value or "LAMP").strip().upper()
    if source_type not in SOURCE_TYPES:
        raise ValueError("source_type must be SUN_WINDOW, LAMP, SCREEN, or OUTDOOR_HDRI")
    return source_type


def _safe_path(raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    if not isinstance(raw_path, str) or not raw_path.strip() or "://" in raw_path or raw_path.startswith("\\\\"):
        raise ValueError("hdri_path must be a local filesystem path")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"hdri_path does not exist: {path}")
    return path


def _object(bpy: Any, name: str) -> Any:
    return bpy.data.objects.get(name)


def _custom_get(target: Any, key: str, default: Any = None) -> Any:
    getter = getattr(target, "get", None)
    if callable(getter):
        return getter(key, default)
    return default


def _remove_owned_lights(bpy: Any, keep_name: str) -> None:
    for obj in list(bpy.data.objects):
        if (
            getattr(obj, "type", None) == "LIGHT"
            and _custom_get(obj, "dcc_mcp_photographic_source", False)
            and obj.name != keep_name
        ):
            bpy.data.objects.remove(obj, do_unlink=True)


def _create_light(bpy: Any, scene: Any, name: str, light_type: str) -> Any:
    obj = _object(bpy, name)
    if obj is not None and getattr(obj, "type", None) != "LIGHT":
        raise ValueError(f"'{name}' already exists and is not a light")
    if obj is None:
        data = bpy.data.lights.new(f"{name} Data", type=light_type)
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
    elif getattr(obj.data, "type", None) != light_type:
        raise ValueError(f"'{name}' is a {getattr(obj.data, 'type', None)} light, expected {light_type}")
    return obj


def _configure_light(
    obj: Any,
    source_type: str,
    energy: float,
    color: list[float],
    location: list[float],
    rotation_degrees: list[float],
) -> dict[str, Any]:
    light = obj.data
    light.energy = energy
    light.color = color
    obj.location = location
    obj.rotation_euler = [math.radians(value) for value in rotation_degrees]
    if hasattr(light, "use_shadow"):
        light.use_shadow = True
    if source_type == "SUN_WINDOW":
        light.shape = "RECTANGLE"
        light.size = 0.8
        if hasattr(light, "size_y"):
            light.size_y = 0.8
    elif source_type == "LAMP":
        light.shadow_soft_size = 0.02
    elif source_type == "SCREEN":
        light.shape = "RECTANGLE"
        light.size = 0.5
        if hasattr(light, "size_y"):
            light.size_y = 0.5
    else:
        light.angle = math.radians(SUN_ANGLE_DEGREES)
    obj["dcc_mcp_photographic_source"] = True
    obj["dcc_mcp_photographic_source_type"] = source_type
    obj["dcc_mcp_photographic_contract"] = "v1"
    return {
        "name": obj.name,
        "type": light.type,
        "source_type": source_type,
        "energy": float(light.energy),
        "color": list(light.color),
        "location": list(obj.location),
        "rotation_degrees": rotation_degrees,
        "angle_degrees": math.degrees(light.angle) if light.type == "SUN" else None,
    }


def _set_world(bpy: Any, scene: Any, image_path: Path, strength: float, rotation_degrees: float) -> dict[str, Any]:
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("DCC Photographic World")
        scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    for node in list(nodes):
        if str(getattr(node, "name", "")).startswith(PREFIX):
            nodes.remove(node)
    environment = nodes.new(type="ShaderNodeTexEnvironment")
    environment.name = f"{PREFIX}HDRI Environment"
    environment.label = environment.name
    environment.image = bpy.data.images.load(str(image_path), check_existing=True)
    texcoord = nodes.new(type="ShaderNodeTexCoord")
    texcoord.name = f"{PREFIX}HDRI Coordinates"
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.name = f"{PREFIX}HDRI Rotation"
    mapping.inputs["Rotation"].default_value[2] = math.radians(rotation_degrees)
    background = nodes.new(type="ShaderNodeBackground")
    background.name = f"{PREFIX}HDRI Background"
    background.label = background.name
    background.inputs["Strength"].default_value = strength
    output = nodes.get("World Output")
    if output is None:
        output = nodes.new(type="ShaderNodeOutputWorld")
        output.name = "World Output"
    for link in list(output.inputs["Surface"].links):
        links.remove(link)
    links.new(texcoord.outputs["Normal"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], environment.inputs["Vector"])
    links.new(environment.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    world["dcc_mcp_photographic_hdri"] = True
    world["dcc_mcp_photographic_hdri_path"] = str(image_path)
    world["dcc_mcp_photographic_hdri_rotation_degrees"] = rotation_degrees
    return {
        "image_path": str(image_path),
        "strength": float(background.inputs["Strength"].default_value),
        "rotation_degrees": rotation_degrees,
        "node_names": [texcoord.name, mapping.name, environment.name, background.name, output.name],
    }


def _set_agx(scene: Any) -> dict[str, Any]:
    settings = scene.view_settings
    settings.view_transform = "AgX"
    try:
        settings.look = "AgX - Medium High Contrast"
    except (TypeError, ValueError):
        pass
    settings.exposure = 0.0
    return {
        "view_transform": getattr(settings, "view_transform", None),
        "look": getattr(settings, "look", None),
        "exposure": float(getattr(settings, "exposure", 0.0)),
    }


def _base_color(obj: Any) -> list[float] | None:
    data = getattr(obj, "data", None)
    materials = getattr(data, "materials", None)
    material = materials[0] if materials and len(materials) else None
    if material is None or not getattr(material, "use_nodes", False):
        color = getattr(obj, "color", None)
        return list(color[:3]) if color is not None else None
    for node in material.node_tree.nodes:
        if getattr(node, "type", None) != "BSDF_PRINCIPLED":
            continue
        socket = node.inputs.get("Base Color")
        if socket is not None and getattr(socket, "default_value", None) is not None:
            return list(socket.default_value[:3])
    return None


def _color_relation(bpy: Any, hero_name: str | None, background_name: str | None) -> dict[str, Any] | None:
    if not hero_name or not background_name:
        return None
    hero = _object(bpy, hero_name)
    background = _object(bpy, background_name)
    if hero is None or background is None:
        return {"hero": None, "background": None, "background_darker_or_cooler": False}
    hero_color = _base_color(hero)
    background_color = _base_color(background)
    if hero_color is None or background_color is None:
        return {"hero": hero_color, "background": background_color, "background_darker_or_cooler": None}
    hero_luminance = 0.2126 * hero_color[0] + 0.7152 * hero_color[1] + 0.0722 * hero_color[2]
    background_luminance = 0.2126 * background_color[0] + 0.7152 * background_color[1] + 0.0722 * background_color[2]
    hero_temperature = hero_color[2] - hero_color[0]
    background_temperature = background_color[2] - background_color[0]
    darker = background_luminance < hero_luminance
    cooler = background_temperature > hero_temperature
    return {
        "hero": hero_color,
        "background": background_color,
        "hero_luminance": hero_luminance,
        "background_luminance": background_luminance,
        "background_darker": darker,
        "background_cooler": cooler,
        "background_darker_or_cooler": darker or cooler,
    }


def analyze_photographic_test_still(
    image_path: str,
    highlight_threshold: float = DEFAULT_HIGHLIGHT_THRESHOLD,
    saturation_threshold: float = DEFAULT_SATURATION_THRESHOLD,
    warm_bias_threshold: float = DEFAULT_WARM_BIAS_THRESHOLD,
    warning_ratio: float = 0.10,
    max_samples: int = DEFAULT_MAX_SAMPLES,
    source_name: str | None = None,
) -> dict:
    """Analyze a rendered preview still for warm saturated highlight bias."""
    try:
        path = _safe_path(image_path)
        if path is None:
            raise ValueError("image_path is required")
        if not isinstance(max_samples, int) or isinstance(max_samples, bool) or max_samples < 1:
            raise ValueError("max_samples must be a positive integer")

        import bpy

        before_ids = {id(image) for image in getattr(bpy.data, "images", ())}
        image = bpy.data.images.load(str(path), check_existing=True)
        created = id(image) not in before_ids
        colorspace = getattr(image, "colorspace_settings", None)
        old_colorspace = getattr(colorspace, "name", None)
        try:
            if colorspace is not None and hasattr(colorspace, "name"):
                try:
                    colorspace.name = "Non-Color"
                except (TypeError, ValueError):
                    pass
            pixels = image.pixels
            result = analyze_rgb_pixels(
                pixels,
                channels=4,
                highlight_threshold=highlight_threshold,
                saturation_threshold=saturation_threshold,
                warm_bias_threshold=warm_bias_threshold,
                warning_ratio=warning_ratio,
                max_samples=max_samples,
            )
        finally:
            if colorspace is not None and old_colorspace is not None:
                try:
                    colorspace.name = old_colorspace
                except (TypeError, ValueError):
                    pass
            if created and getattr(image, "users", 0) == 0:
                try:
                    bpy.data.images.remove(image)
                except (RuntimeError, TypeError):
                    pass

        source = None
        if source_name:
            light = _object(bpy, source_name)
            if light is not None and getattr(light, "type", None) == "LIGHT":
                source = {
                    "name": light.name,
                    "energy": float(getattr(light.data, "energy", 0.0)),
                    "source_type": _custom_get(light, "dcc_mcp_photographic_source_type"),
                }
        return skill_success(
            "Photographic test still color safety analyzed",
            image_path=str(path),
            source=source,
            color_safety=result,
            prompt=result["recommendation"],
        )
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid photographic test still analysis request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to analyze photographic test still")


def configure_motivated_lighting(
    source_name: str,
    source_type: str = "LAMP",
    energy: float = 120.0,
    color: Any = None,
    location: Any = None,
    rotation_degrees: Any = None,
    hdri_path: str | None = None,
    hdri_strength: float = 0.35,
    hdri_rotation_degrees: float = 0.0,
    hero_object: str | None = None,
    background_object: str | None = None,
) -> dict:
    """Create one motivated key source and optional outdoor HDRI environment."""
    try:
        kind = _normalise_source_type(source_type)
        light_energy = _finite(energy, "energy")
        if light_energy <= 0:
            raise ValueError("energy must be greater than zero")
        key_color = _color(color, "color", (1.0, 0.92, 0.8) if kind in {"SUN_WINDOW", "LAMP"} else (1.0, 1.0, 1.0))
        key_location = _vector(location, "location", (0.0, -1.0, 1.0))
        key_rotation = _vector(rotation_degrees, "rotation_degrees", (35.0, 0.0, 25.0))
        strength = _finite(hdri_strength, "hdri_strength")
        if strength <= 0:
            raise ValueError("hdri_strength must be greater than zero")
        hdri = _safe_path(hdri_path)
        if kind == "OUTDOOR_HDRI" and hdri is None:
            raise ValueError("OUTDOOR_HDRI requires hdri_path")
        import bpy

        scene = bpy.context.scene
        _remove_owned_lights(bpy, source_name)
        obj = _create_light(bpy, scene, source_name, SOURCE_LIGHT_TYPES[kind])
        light = _configure_light(obj, kind, light_energy, key_color, key_location, key_rotation)
        world = None
        if kind == "OUTDOOR_HDRI" and hdri is not None:
            world = _set_world(bpy, scene, hdri, strength, _finite(hdri_rotation_degrees, "hdri_rotation_degrees"))
        view = _set_agx(scene)
        relation = _color_relation(bpy, hero_object, background_object)
        return skill_success(
            f"Motivated photographic lighting configured: {source_name}",
            source=light,
            world=world,
            view_settings=view,
            hero_background=relation,
            source_contract={
                "motivated_source": kind,
                "outdoor_sun_angle_degrees": SUN_ANGLE_DEGREES if kind == "OUTDOOR_HDRI" else None,
                "agx_view_transform": "AgX",
                "agx_look": "AgX - Medium High Contrast",
                "exposure": 0.0,
            },
            saturated_color_check={
                "performed": False,
                "requires_preview_still": True,
                "instruction": "Render a 25% test still at 32 samples and lower key energy if saturated colors clip warm under AgX. Preserve material color.",
            },
            prompt="Validate the lighting before rendering. Keep the hero in front of a darker or cooler background.",
        )
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid motivated lighting request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to configure motivated lighting: {source_name}")


def validate_motivated_lighting(
    source_name: str,
    source_type: str = "LAMP",
    hero_object: str | None = None,
    background_object: str | None = None,
    require_agx: bool = True,
    preview_still_path: str | None = None,
) -> dict:
    """Read-only validation for motivated source, HDRI, AgX, and contrast setup."""
    try:
        kind = _normalise_source_type(source_type)
        import bpy

        source = _object(bpy, source_name)
        if source is None:
            return skill_error("Light not found", f"No object named '{source_name}' exists.")
        issues = []

        def issue(code: str, field: str, expected: Any, actual: Any, message: str, severity: str = "error") -> None:
            issues.append(
                {
                    "code": code,
                    "severity": severity,
                    "field": field,
                    "expected": expected,
                    "actual": actual,
                    "message": message,
                }
            )

        expected_type = SOURCE_LIGHT_TYPES[kind]
        if getattr(source, "type", None) != "LIGHT" or getattr(source.data, "type", None) != expected_type:
            issue(
                "MOTIVATED_SOURCE_TYPE_MISMATCH",
                "light_type",
                expected_type,
                getattr(getattr(source, "data", None), "type", None),
                "The motivated source uses the wrong Blender light type.",
            )
        actual_source_type = _custom_get(source, "dcc_mcp_photographic_source_type")
        if actual_source_type != kind:
            issue(
                "MOTIVATED_SOURCE_METADATA_MISSING",
                "source_type",
                kind,
                actual_source_type,
                "Configure the light through the photographic lighting skill.",
            )
        if getattr(source.data, "energy", 0.0) <= 0:
            issue(
                "MOTIVATED_SOURCE_DISABLED",
                "energy",
                "> 0",
                getattr(source.data, "energy", None),
                "The motivated source must emit light.",
            )
        if kind == "OUTDOOR_HDRI":
            actual_angle = math.degrees(float(getattr(source.data, "angle", 0.0)))
            if not math.isclose(actual_angle, SUN_ANGLE_DEGREES, abs_tol=1e-4):
                issue(
                    "OUTDOOR_SUN_ANGLE_MISMATCH",
                    "angle_degrees",
                    SUN_ANGLE_DEGREES,
                    actual_angle,
                    "Outdoor sun angle should be about 1.2 degrees.",
                )
            world = bpy.context.scene.world
            env = None
            if world is not None and getattr(world, "use_nodes", False):
                env = next(
                    (
                        node
                        for node in world.node_tree.nodes
                        if str(getattr(node, "name", "")).startswith(f"{PREFIX}HDRI Environment")
                    ),
                    None,
                )
            if env is None or getattr(env, "image", None) is None:
                issue(
                    "OUTDOOR_HDRI_MISSING",
                    "hdri_environment",
                    True,
                    False,
                    "Outdoor lighting requires a loaded HDRI environment.",
                )
        view_settings = bpy.context.scene.view_settings
        if require_agx and getattr(view_settings, "view_transform", None) != "AgX":
            issue(
                "VIEW_TRANSFORM_MISMATCH",
                "view_transform",
                "AgX",
                getattr(view_settings, "view_transform", None),
                "Use AgX for saturated toy colors.",
            )
        if require_agx and getattr(view_settings, "look", None) != "AgX - Medium High Contrast":
            issue(
                "VIEW_LOOK_MISMATCH",
                "look",
                "AgX - Medium High Contrast",
                getattr(view_settings, "look", None),
                "Use the specified AgX contrast look.",
            )
        if require_agx and not math.isclose(float(getattr(view_settings, "exposure", 0.0)), 0.0, abs_tol=1e-6):
            issue(
                "VIEW_EXPOSURE_MISMATCH",
                "exposure",
                0.0,
                getattr(view_settings, "exposure", None),
                "Keep exposure at zero and lower light energy when colors clip.",
            )
        relation = _color_relation(bpy, hero_object, background_object)
        if relation is not None and relation.get("background_darker_or_cooler") is False:
            issue(
                "HERO_BACKGROUND_CONTRAST_MISSING",
                "hero_background",
                "background darker or cooler",
                relation,
                "Place the hero in front of something darker or cooler.",
                "warning",
            )
        owned_sources = [
            obj
            for obj in bpy.data.objects
            if getattr(obj, "type", None) == "LIGHT" and _custom_get(obj, "dcc_mcp_photographic_source", False)
        ]
        if kind != "OUTDOOR_HDRI" and len(owned_sources) != 1:
            issue(
                "MULTIPLE_MOTIVATED_SOURCES",
                "owned_light_count",
                1,
                len(owned_sources),
                "Keep one motivated source per scene.",
            )
        color_safety = {
            "performed": False,
            "preview_still_required": True,
            "instruction": "If saturated colors clip warm, lower key energy and keep material color unchanged.",
        }
        if preview_still_path:
            analysis = analyze_photographic_test_still(
                image_path=preview_still_path,
                source_name=source_name,
            )
            if not analysis.get("success"):
                issue(
                    "COLOR_SAFETY_ANALYSIS_FAILED",
                    "preview_still_path",
                    "readable rendered preview still",
                    analysis.get("error"),
                    "The supplied preview still could not be analyzed.",
                )
            else:
                color_safety = analysis.get("context", {}).get("color_safety", {})
                if color_safety.get("recommend_lower_key_energy"):
                    issue(
                        "WARM_SATURATED_HIGHLIGHTS",
                        "preview_still_path",
                        "warm_highlight_ratio below warning ratio",
                        color_safety,
                        "Lower the motivated key energy and preserve the material color.",
                        "warning",
                    )
        return skill_success(
            f"Motivated photographic lighting validation completed: {source_name}",
            valid=not any(item["severity"] == "error" for item in issues),
            source={
                "name": source.name,
                "type": source.data.type,
                "energy": float(source.data.energy),
                "color": list(source.data.color),
                "angle_degrees": math.degrees(float(source.data.angle)) if source.data.type == "SUN" else None,
            },
            hero_background=relation,
            color_safety={
                "view_transform": getattr(view_settings, "view_transform", None),
                "look": getattr(view_settings, "look", None),
                "exposure": float(getattr(view_settings, "exposure", 0.0)),
                **color_safety,
            },
            issues=issues,
        )
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid motivated lighting validation request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to validate motivated lighting: {source_name}")
