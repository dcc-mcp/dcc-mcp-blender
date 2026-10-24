"""Small version/feature boundary shared by compositor readers and writers."""

from __future__ import annotations

from typing import Any


def modern_compositor(bpy: Any, scene: Any) -> bool:
    """Blender 5.0 moved the compositor into an independently owned node group."""
    version = tuple(getattr(bpy.app, "version", (0, 0, 0)))
    if version >= (5, 3, 0):
        raise ValueError(
            "Compositor tools currently support the pre-5.3 scene API; Blender 5.3+ effects stacks require a separate adapter"
        )
    modern = version >= (5, 0, 0)
    if modern and not hasattr(scene, "compositing_node_group"):
        raise ValueError("This Blender 5.x host exposes no scene.compositing_node_group API")
    return modern


def compositor_tree(bpy: Any, scene: Any) -> Any:
    if modern_compositor(bpy, scene):
        return scene.compositing_node_group
    return getattr(scene, "node_tree", None)


def compositor_enabled(bpy: Any, scene: Any) -> bool:
    if modern_compositor(bpy, scene):
        return bool(scene.render.use_compositing)
    return bool(getattr(scene, "use_nodes", False))


def require_local_scene(scene: Any) -> None:
    if getattr(scene, "library", None) is not None or getattr(scene, "override_library", None) is not None:
        raise ValueError("Linked/override scenes cannot be edited by these compositor tools")


def require_single_user_tree(tree: Any) -> None:
    if getattr(tree, "library", None) is not None or getattr(tree, "override_library", None) is not None:
        raise ValueError("Linked/override compositor groups cannot be edited by these tools")
    real_users = getattr(tree, "users", 0) - int(bool(getattr(tree, "use_fake_user", False)))
    if real_users > 1:
        raise ValueError("Compositor group has multiple users; make it single-user before editing")


def set_compositor_state(bpy: Any, scene: Any, enabled: bool) -> None:
    require_local_scene(scene)
    modern = modern_compositor(bpy, scene)
    owner, prop = (scene.render, "use_compositing") if modern else (scene, "use_nodes")
    previous = getattr(owner, prop)
    try:
        setattr(owner, prop, bool(enabled))
        if bool(getattr(owner, prop)) != bool(enabled):
            raise ValueError("Blender did not retain the requested compositor enabled state")
    except Exception:
        setattr(owner, prop, previous)
        raise
