"""Blender scene assembly operations: merge, link/append, view layers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_VIEW_LAYER_PASSES = {
    "z": ("layer", "use_pass_z"),
    "mist": ("layer", "use_pass_mist"),
    "normal": ("layer", "use_pass_normal"),
    "vector": ("layer", "use_pass_vector"),
    "diffuse_direct": ("layer", "use_pass_diffuse_direct"),
    "diffuse_indirect": ("layer", "use_pass_diffuse_indirect"),
    "diffuse_color": ("layer", "use_pass_diffuse_color"),
    "glossy_direct": ("layer", "use_pass_glossy_direct"),
    "glossy_indirect": ("layer", "use_pass_glossy_indirect"),
    "glossy_color": ("layer", "use_pass_glossy_color"),
    "transmission_direct": ("layer", "use_pass_transmission_direct"),
    "transmission_indirect": ("layer", "use_pass_transmission_indirect"),
    "transmission_color": ("layer", "use_pass_transmission_color"),
    "emit": ("layer", "use_pass_emit"),
    "environment": ("layer", "use_pass_environment"),
    "cryptomatte_object": ("layer", "use_pass_cryptomatte_object"),
    "cryptomatte_material": ("layer", "use_pass_cryptomatte_material"),
    "cryptomatte_asset": ("layer", "use_pass_cryptomatte_asset"),
    "volume_direct": ("cycles", "use_pass_volume_direct"),
    "volume_indirect": ("cycles", "use_pass_volume_indirect"),
}


def _find_layer_collection(root: Any, name: str) -> Any | None:
    stack = [root]
    while stack:
        item = stack.pop()
        if item.collection.name == name:
            return item
        stack.extend(item.children)
    return None


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


def configure_view_layer(
    name: str,
    scene_name: str | None = None,
    enabled: bool | None = None,
    passes: list[str] | None = None,
    exclude_collections: list[str] | None = None,
    include_collections: list[str] | None = None,
    cryptomatte_depth: int | None = None,
) -> dict:
    """Configure render passes and collection visibility for one view layer."""
    if not name:
        return skill_error("Invalid name", "name must be a non-empty string.")
    requested_passes = list(dict.fromkeys(passes or []))
    unknown_passes = sorted(set(requested_passes) - set(_VIEW_LAYER_PASSES))
    if unknown_passes:
        return skill_error(
            "Unsupported view-layer pass",
            "Unsupported passes: {}. Supported passes: {}.".format(
                ", ".join(unknown_passes), ", ".join(sorted(_VIEW_LAYER_PASSES))
            ),
        )
    if cryptomatte_depth is not None and not 2 <= cryptomatte_depth <= 16:
        return skill_error("Invalid Cryptomatte depth", "cryptomatte_depth must be between 2 and 16.")

    try:
        import bpy

        scene = bpy.context.scene if scene_name is None else bpy.data.scenes.get(scene_name)
        if scene is None:
            return skill_error(f"Scene not found: {scene_name}", f"No scene named '{scene_name}'.")
        if name not in scene.view_layers:
            return skill_error(
                f"View layer not found: {name}",
                f"Scene '{scene.name}' has no view layer named '{name}'.",
            )
        layer = scene.view_layers[name]

        collection_changes: list[tuple[Any, bool]] = []
        missing_collections: list[str] = []
        for collection_name, excluded in (
            *((value, True) for value in (exclude_collections or [])),
            *((value, False) for value in (include_collections or [])),
        ):
            layer_collection = _find_layer_collection(layer.layer_collection, collection_name)
            if layer_collection is None:
                missing_collections.append(collection_name)
            else:
                collection_changes.append((layer_collection, excluded))
        if missing_collections:
            return skill_error(
                "Collection not found in view layer",
                "Missing collections: {}.".format(", ".join(sorted(set(missing_collections)))),
            )

        pass_targets = {
            pass_name: layer if target_name == "layer" else getattr(layer, "cycles", None)
            for pass_name, (target_name, _) in _VIEW_LAYER_PASSES.items()
        }
        unsupported_in_host = [
            pass_name
            for pass_name in requested_passes
            if pass_targets[pass_name] is None or not hasattr(pass_targets[pass_name], _VIEW_LAYER_PASSES[pass_name][1])
        ]
        if unsupported_in_host:
            return skill_error(
                "View-layer pass unavailable in this Blender version",
                "Unavailable passes: {}.".format(", ".join(unsupported_in_host)),
            )

        if enabled is not None:
            layer.use = enabled
        for pass_name in requested_passes:
            setattr(pass_targets[pass_name], _VIEW_LAYER_PASSES[pass_name][1], True)
        for layer_collection, excluded in collection_changes:
            layer_collection.exclude = excluded
        if cryptomatte_depth is not None:
            layer.pass_cryptomatte_depth = cryptomatte_depth

        return skill_success(
            f"Configured view layer {name}",
            scene_name=scene.name,
            view_layer_name=name,
            enabled=getattr(layer, "use", True),
            enabled_passes=requested_passes,
            excluded_collections=[item.collection.name for item, excluded in collection_changes if excluded],
            included_collections=[item.collection.name for item, excluded in collection_changes if not excluded],
            cryptomatte_depth=getattr(layer, "pass_cryptomatte_depth", None),
            prompt="Use list_view_layers to inspect layers before rendering a multilayer EXR.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to configure view layer {name}")


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
