"""Blender scene assembly operations: merge, link/append, view layers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success


def _iter_items(data_from: Any, attr: str) -> list[str]:
    try:
        items = getattr(data_from, attr)
        if items:
            return list(items)
    except Exception:
        pass
    return []


def merge_scene(filepath: str, import_all: bool = True) -> dict:
    """Merge data from an external .blend file into the current scene."""
    path = Path(filepath).expanduser()
    if not path.suffix:
        path = path.with_suffix(".blend")
    if not path.is_file():
        return skill_error(f"File not found: {path}", f"No .blend file at '{path}'.")

    try:
        import bpy

        with bpy.data.libraries.load(str(path)) as (data_from, data_to):
            if import_all:
                for attr in dir(data_from):
                    if attr.startswith("_"):
                        continue
                    try:
                        items = _iter_items(data_from, attr)
                        if items:
                            setattr(data_to, attr, items)
                    except Exception:
                        pass

        return skill_success(
            f"Merged data from {path.name}",
            filepath=str(path),
            import_all=import_all,
            prompt="Use blender-collection or blender-scene tools to inspect merged content.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to merge scene from {filepath}")


def _append_common(
    filepath: str,
    data_type: str,
    names: list[str] | None = None,
    link: bool = False,
) -> dict:
    """Internal: append or link data blocks from an external .blend file."""
    valid_types = {
        "objects",
        "collections",
        "materials",
        "meshes",
        "lights",
        "cameras",
        "worlds",
        "node_groups",
        "actions",
        "armatures",
    }
    data_type_key = data_type.lower()
    if data_type_key not in valid_types:
        return skill_error(
            f"Unsupported data type: {data_type}",
            f"Supported types: {', '.join(sorted(valid_types))}.",
        )

    path = Path(filepath).expanduser()
    if not path.suffix:
        path = path.with_suffix(".blend")
    if not path.is_file():
        return skill_error(f"File not found: {path}", f"No .blend file at '{path}'.")

    try:
        import bpy

        dataname = data_type_key
        if dataname == "node_groups":
            dataname = "nodeGroups"

        with bpy.data.libraries.load(str(path), link=link) as (data_from, data_to):
            src_items = _iter_items(data_from, dataname)
            if names:
                items = [n for n in names if n in src_items]
            else:
                items = list(src_items)
            setattr(data_to, dataname, items)

        return skill_success(
            f"{'Linked' if link else 'Appended'} {len(items)} {data_type_key} from {path.name}",
            filepath=str(path),
            data_type=data_type_key,
            names=items,
            link=bool(link),
            count=len(items),
            prompt="Use blender-collection or blender-scene tools to organize the imported data.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to append from {filepath}")


def append_from_blend(
    filepath: str,
    data_type: str = "objects",
    names: list[str] | None = None,
) -> dict:
    """Append data blocks from an external .blend file."""
    return _append_common(filepath=filepath, data_type=data_type, names=names, link=False)


def link_from_blend(
    filepath: str,
    data_type: str = "collections",
    names: list[str] | None = None,
) -> dict:
    """Link data blocks from an external .blend file (library reference)."""
    return _append_common(filepath=filepath, data_type=data_type, names=names, link=True)


def list_view_layers(scene_name: str | None = None) -> dict:
    """List view layers in a scene."""
    try:
        import bpy

        scenes_to_check = [bpy.context.scene]
        if scene_name:
            scene = bpy.data.scenes.get(scene_name)
            if scene is None:
                return skill_error(f"Scene not found: {scene_name}", f"No scene named '{scene_name}'.")
            scenes_to_check = [scene]
        else:
            scenes_to_check = list(bpy.data.scenes)

        result = []
        for scene in scenes_to_check:
            layers = []
            for vl in scene.view_layers:
                layers.append(
                    {
                        "name": vl.name,
                        "use": getattr(vl, "use", True),
                        "is_active": vl == bpy.context.view_layer,
                    }
                )
            result.append(
                {
                    "scene_name": scene.name,
                    "view_layers": layers,
                    "count": len(layers),
                }
            )

        return skill_success(
            f"Found {sum(r['count'] for r in result)} view layer(s)",
            scenes=result,
            total=sum(r["count"] for r in result),
            prompt="Use set_active_view_layer or create_view_layer to manage layers.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list view layers")


def create_view_layer(name: str, scene_name: str | None = None) -> dict:
    """Create a new view layer in a scene."""
    if not name:
        return skill_error("Invalid name", "name must be a non-empty string.")
    try:
        import bpy

        scene = bpy.context.scene
        if scene_name:
            scene = bpy.data.scenes.get(scene_name)
            if scene is None:
                return skill_error(f"Scene not found: {scene_name}", f"No scene named '{scene_name}'.")

        if name in scene.view_layers:
            return skill_error(
                f"View layer already exists: {name}",
                f"Scene '{scene.name}' already has a view layer named '{name}'.",
            )

        vl = scene.view_layers.new(name)
        return skill_success(
            f"Created view layer {name}",
            scene_name=scene.name,
            view_layer_name=vl.name,
            prompt="Use list_view_layers to inspect layers or set_active_view_layer to switch.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create view layer {name}")


def remove_view_layer(name: str, scene_name: str | None = None) -> dict:
    """Remove a view layer from a scene."""
    if not name:
        return skill_error("Invalid name", "name must be a non-empty string.")
    try:
        import bpy

        scene = bpy.context.scene
        if scene_name:
            scene = bpy.data.scenes.get(scene_name)
            if scene is None:
                return skill_error(f"Scene not found: {scene_name}", f"No scene named '{scene_name}'.")

        if name not in scene.view_layers:
            return skill_error(
                f"View layer not found: {name}",
                f"Scene '{scene.name}' has no view layer named '{name}'.",
            )

        if len(scene.view_layers) <= 1:
            return skill_error(
                "Cannot remove last view layer",
                "A scene must have at least one view layer.",
            )

        vl = scene.view_layers[name]
        scene.view_layers.remove(vl)
        return skill_success(
            f"Removed view layer {name}",
            scene_name=scene.name,
            view_layer_name=name,
            prompt="Use list_view_layers to verify the current view layers.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to remove view layer {name}")


def set_active_view_layer(name: str, scene_name: str | None = None) -> dict:
    """Set the active view layer."""
    if not name:
        return skill_error("Invalid name", "name must be a non-empty string.")
    try:
        import bpy

        scene = bpy.context.scene
        if scene_name:
            scene = bpy.data.scenes.get(scene_name)
            if scene is None:
                return skill_error(f"Scene not found: {scene_name}", f"No scene named '{scene_name}'.")

        if name not in scene.view_layers:
            return skill_error(
                f"View layer not found: {name}",
                f"Scene '{scene.name}' has no view layer named '{name}'.",
            )

        bpy.context.window.view_layer = scene.view_layers[name]
        return skill_success(
            f"Set active view layer to {name}",
            scene_name=scene.name,
            view_layer_name=name,
            prompt="Use list_view_layers to inspect all layers in the scene.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set active view layer {name}")


def list_external_references() -> dict:
    """List all external .blend file references (library linking)."""
    try:
        import bpy

        refs = []
        for lib in bpy.data.libraries:
            refs.append(
                {
                    "name": lib.name,
                    "filepath": lib.filepath,
                    "is_relative": getattr(lib, "is_relative", False),
                }
            )

        return skill_success(
            f"Found {len(refs)} external reference(s)",
            references=refs,
            count=len(refs),
            prompt="Use append_from_blend or link_from_blend to import external data.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list external references")
