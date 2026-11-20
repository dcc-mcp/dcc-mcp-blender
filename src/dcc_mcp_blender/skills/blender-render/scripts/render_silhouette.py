"""Render a temporary Workbench silhouette without changing scene state."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_DEFAULT_OBJECT_TYPES = ("MESH", "FONT")
_SHADING_ATTRIBUTES = (
    "light",
    "color_type",
    "single_color",
    "show_shadows",
    "show_cavity",
    "show_specular_highlight",
    "background_type",
    "background_color",
)


def _items(value: Any) -> Iterable[Any]:
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _names(value: Any) -> List[str]:
    if value is None:
        return []
    values = [value] if isinstance(value, str) else value
    result: List[str] = []
    for item in values or []:
        name = str(item).strip()
        if name and name not in result:
            result.append(name)
    return result


def _rgb(value: Any, label: str) -> tuple[float, float, float]:
    try:
        values = [float(item) for item in value]
    except (TypeError, ValueError):
        raise ValueError(f"{label} must contain three numeric values.")
    if len(values) != 3 or any(value < 0 or value > 1 for value in values):
        raise ValueError(f"{label} must contain exactly three values in the range 0..1.")
    return tuple(values)


def _snapshot(scene: Any, objects: List[Any]) -> Dict[str, Any]:
    render = scene.render
    image_settings = render.image_settings
    world = getattr(scene, "world", None)
    shading = getattr(getattr(scene, "display", None), "shading", None)
    return {
        "render": {
            "engine": getattr(render, "engine", None),
            "filepath": getattr(render, "filepath", None),
            "film_transparent": getattr(render, "film_transparent", None),
            "resolution_x": getattr(render, "resolution_x", None),
            "resolution_y": getattr(render, "resolution_y", None),
            "resolution_percentage": getattr(render, "resolution_percentage", None),
            "file_format": getattr(image_settings, "file_format", None),
            "color_mode": getattr(image_settings, "color_mode", None),
        },
        "view": {
            "view_transform": getattr(getattr(scene, "view_settings", None), "view_transform", None),
            "look": getattr(getattr(scene, "view_settings", None), "look", None),
        },
        "world_color": tuple(getattr(world, "color", ())) if world is not None else None,
        "shading": {
            attribute: getattr(shading, attribute)
            for attribute in _SHADING_ATTRIBUTES
            if shading is not None and hasattr(shading, attribute)
        },
        "hide_render": {str(getattr(obj, "name", "")): bool(getattr(obj, "hide_render", False)) for obj in objects},
    }


def _restore(scene: Any, objects: List[Any], state: Dict[str, Any]) -> None:
    render = scene.render
    image_settings = render.image_settings
    for attribute, value in state["render"].items():
        target = image_settings if attribute in {"file_format", "color_mode"} else render
        if value is not None:
            setattr(target, attribute, value)
    view_settings = getattr(scene, "view_settings", None)
    for attribute, value in state["view"].items():
        if view_settings is not None and value is not None:
            setattr(view_settings, attribute, value)
    world = getattr(scene, "world", None)
    if world is not None and state["world_color"] is not None:
        world.color = state["world_color"]
    shading = getattr(getattr(scene, "display", None), "shading", None)
    if shading is not None:
        for attribute, value in state["shading"].items():
            setattr(shading, attribute, value)
    for obj in objects:
        name = str(getattr(obj, "name", ""))
        if name in state["hide_render"]:
            obj.hide_render = state["hide_render"][name]


def render_silhouette(
    output_path: str,
    resolution_x: int = 1400,
    resolution_y: int = 875,
    resolution_percentage: int = 100,
    object_names: Optional[List[str]] = None,
    exclude_name_prefixes: Optional[List[str]] = None,
    object_types: Optional[List[str]] = None,
    object_color: Optional[List[float]] = None,
    background_color: Optional[List[float]] = None,
) -> dict:
    """Render a flat silhouette and restore every temporary scene setting."""
    try:
        import bpy

        if not str(output_path or "").strip():
            return skill_error("Missing output path", "Pass a local output_path for the silhouette image.")
        if resolution_x < 1 or resolution_y < 1 or not 1 <= resolution_percentage <= 100:
            return skill_error(
                "Invalid silhouette resolution", "Resolution values must be positive and percentage must be 1..100."
            )

        include_names = set(_names(object_names))
        excluded_prefixes = tuple(_names(exclude_name_prefixes))
        allowed_types = {item.upper() for item in _names(object_types)} or set(_DEFAULT_OBJECT_TYPES)
        object_color = _rgb(object_color or [0.82, 0.82, 0.82], "object_color")
        background_color = _rgb(background_color or [0.0, 0.0, 0.0], "background_color")

        scene = bpy.context.scene
        objects = list(_items(getattr(scene, "objects", [])))
        state = _snapshot(scene, objects)
        hidden_names: List[str] = []
        try:
            for obj in objects:
                name = str(getattr(obj, "name", ""))
                if str(getattr(obj, "type", "")).upper() not in allowed_types:
                    continue
                should_hide = (bool(include_names) and name not in include_names) or (
                    bool(excluded_prefixes) and name.startswith(excluded_prefixes)
                )
                if should_hide:
                    obj.hide_render = True
                    hidden_names.append(name)

            render = scene.render
            render.engine = "BLENDER_WORKBENCH"
            render.filepath = str(output_path)
            render.film_transparent = False
            render.resolution_x = int(resolution_x)
            render.resolution_y = int(resolution_y)
            render.resolution_percentage = int(resolution_percentage)
            render.image_settings.file_format = "PNG"
            render.image_settings.color_mode = "RGB"

            view_settings = getattr(scene, "view_settings", None)
            if view_settings is not None:
                view_settings.view_transform = "Standard"
                if hasattr(view_settings, "look"):
                    view_settings.look = "None"
            world = getattr(scene, "world", None)
            if world is not None:
                world.color = background_color
            shading = getattr(getattr(scene, "display", None), "shading", None)
            if shading is not None:
                for attribute, value in {
                    "light": "FLAT",
                    "color_type": "SINGLE",
                    "single_color": object_color,
                    "show_shadows": False,
                    "show_cavity": False,
                    "show_specular_highlight": False,
                    "background_type": "WORLD",
                    "background_color": background_color,
                }.items():
                    if hasattr(shading, attribute):
                        setattr(shading, attribute, value)

            bpy.ops.render.render(write_still=True)
            return skill_success(
                "Silhouette rendered",
                output_path=str(output_path),
                resolution=[int(resolution_x), int(resolution_y)],
                object_types=sorted(allowed_types),
                hidden_object_names=hidden_names,
                prompt="Silhouette rendered. Temporary render and visibility settings were restored.",
            )
        finally:
            _restore(scene, objects, state)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except ValueError as exc:
        return skill_error("Invalid silhouette settings", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to render silhouette")


@skill_entry
def main(**kwargs) -> dict:
    return render_silhouette(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
