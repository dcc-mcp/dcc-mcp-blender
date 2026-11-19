"""Photographic compositor finishing for Blender 5 toy shots."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._compositor_compat import modern_compositor
from dcc_mcp_blender._compositor_ops import (
    _R_LAYERS_NODE,
    _group_output_input,
    _resolve_compositor_tree,
    setup_compositor_tree,
)
from dcc_mcp_blender._node_graph_ops import (
    _collection_get,
    _create_node_in_tree,
    _get_socket,
    _iter_collection,
    _node_type,
    _remove_link,
    _remove_node,
)

POST_VERSION = "dcc-mcp-blender.photographic-post.v1"
POST_PREFIX = "DCC Photo Post "
GRAIN_CONFIG_KEY = "dcc_mcp_photographic_post_grain"
CONTRACT_KEY = "dcc_mcp_photographic_post_contract"
SETTINGS_KEY = "dcc_mcp_photographic_post_settings"
_MISSING = object()
DEFAULT_HALATION_THRESHOLD = 185.0 / 255.0
DEFAULT_HALATION_TINT = (1.0, 0.82, 0.62)
DEFAULT_HALATION_MIX = 0.34
DEFAULT_VIGNETTE_STRENGTH = 0.20
DEFAULT_GRAIN_STRENGTH = 0.015
DEFAULT_GRAIN_SIZE = 256
DEFAULT_GRAIN_SEED = 1337


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


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _bounded(value: Any, label: str, minimum: float = 0.0, maximum: float = 1.0) -> float:
    result = _finite(value, label)
    if result < minimum or result > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return result


def _rgb(value: Any, label: str) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{label} must contain exactly three finite channels")
    return [_bounded(component, f"{label}[{index}]") for index, component in enumerate(value)]


def _node_is_owned(node: Any) -> bool:
    return str(getattr(node, "name", "")).startswith(POST_PREFIX)


def _owned_nodes(tree: Any) -> list[Any]:
    return [node for node in _iter_collection(tree.nodes) if _node_is_owned(node)]


def _output_node(tree: Any, modern: bool) -> Any | None:
    if modern:
        active = [
            node
            for node in _iter_collection(tree.nodes)
            if _node_type(node) == "NodeGroupOutput" and getattr(node, "is_active_output", False)
        ]
        return (
            active[0]
            if active
            else next((node for node in _iter_collection(tree.nodes) if _node_type(node) == "NodeGroupOutput"), None)
        )
    return _collection_get(tree.nodes, "Composite") or next(
        (node for node in _iter_collection(tree.nodes) if _node_type(node) == "CompositorNodeComposite"), None
    )


def _output_target(tree: Any, output: Any, modern: bool) -> Any | None:
    if modern:
        return _group_output_input(tree, output)
    return _get_socket(getattr(output, "inputs", ()), "Image")


def _image_input(node: Any) -> Any | None:
    for name in ("Image", "A_Color", "A"):
        socket = _get_socket(getattr(node, "inputs", ()), name)
        if socket is not None:
            return socket
    return None


def _image_output(node: Any) -> Any | None:
    for name in ("Image", "Result_Color", "Result", "Glare"):
        socket = _get_socket(getattr(node, "outputs", ()), name)
        if socket is not None:
            return socket
    return None


def _upstream_socket(socket: Any, visited: set[int] | None = None) -> Any | None:
    """Find the first non-owned image source before the output socket."""
    visited = visited or set()
    if socket is None or id(socket) in visited:
        return None
    visited.add(id(socket))
    links = list(getattr(socket, "links", ()) or ())
    if not links:
        return None
    link = links[0]
    node = getattr(link, "from_node", None)
    if node is None or not _node_is_owned(node):
        return getattr(link, "from_socket", None)
    return _upstream_socket(_image_input(node), visited)


def _find_base_source(tree: Any, target: Any, scene: Any) -> Any:
    source = _upstream_socket(target)
    if source is not None:
        return source
    render_layers = _collection_get(tree.nodes, "Render Layers")
    if render_layers is None:
        render_layers = next(
            (node for node in _iter_collection(tree.nodes) if _node_type(node) == _R_LAYERS_NODE), None
        )
    if render_layers is None:
        render_layers = _create_node_in_tree(tree, _R_LAYERS_NODE)
        render_layers.name = "Render Layers"
        render_layers.label = "Render Layers"
        render_layers.scene = scene
    source = _get_socket(getattr(render_layers, "outputs", ()), "Image")
    if source is None:
        raise ValueError("Render Layers has no Image output")
    return source


def _remove_owned_nodes(tree: Any) -> int:
    owned = _owned_nodes(tree)
    for node in owned:
        _remove_node(tree, node)
    return len(owned)


def _candidate_name(name: str) -> str:
    return f"{POST_PREFIX}Candidate {name[len(POST_PREFIX) :]}"


def _restore_scene_property(scene: Any, key: str, value: Any) -> None:
    try:
        if value is _MISSING:
            del scene[key]
        else:
            scene[key] = value
    except (KeyError, TypeError, AttributeError):
        if value is not _MISSING:
            raise


def _new_node(tree: Any, node_type: str, name: str, location: tuple[float, float]) -> Any:
    node = _create_node_in_tree(tree, node_type)
    node.name = name
    node.label = name
    node.location = location
    return node


def _set_input(node: Any, names: tuple[str, ...], value: Any) -> Any:
    for name in names:
        socket = _get_socket(getattr(node, "inputs", ()), name)
        if socket is not None:
            socket.default_value = value
            return socket
    raise ValueError(f"{getattr(node, 'name', 'node')} has no input named {'/'.join(names)}")


def _link(tree: Any, source: Any, target: Any) -> None:
    if source is None or target is None:
        raise ValueError("Cannot connect a missing compositor socket")
    for existing in list(getattr(target, "links", ()) or ()):
        _remove_link(tree, existing)
    tree.links.new(source, target)


def _mix_node(tree: Any, name: str, location: tuple[float, float], blend_type: str = "MIX") -> Any:
    try:
        node = _new_node(tree, "ShaderNodeMix", name, location)
        node.data_type = "RGBA"
        node.blend_type = blend_type
        return node
    except Exception:
        node = _new_node(tree, "CompositorNodeMixRGB", name, location)
        node.blend_type = blend_type
        return node


def _mix_socket(node: Any, role: str) -> Any | None:
    aliases = {
        "factor": ("Factor_Float", "Fac"),
        "a": ("A_Color", "Color1"),
        "b": ("B_Color", "Color2"),
        "result": ("Result_Color", "Image"),
    }
    return _get_socket(
        getattr(node, "inputs", ()) if role != "result" else getattr(node, "outputs", ()), aliases[role][0]
    ) or _get_socket(
        getattr(node, "inputs", ()) if role != "result" else getattr(node, "outputs", ()), aliases[role][1]
    )


def _configure_curve(node: Any) -> list[list[float]]:
    mapping = getattr(node, "mapping", None)
    curves = getattr(mapping, "curves", None)
    if curves is None or len(curves) == 0:
        raise ValueError("CurveRGB does not expose mapping curves")
    curve = curves[-1]
    points = curve.points
    points.new(0.25, 0.18)
    points.new(0.75, 0.82)
    mapping.update()
    return [[0.25, 0.18], [0.75, 0.82]]


def _grain_pixels(size: int, seed: int, frame: int) -> list[float]:
    rng = random.Random(int(seed) + int(frame) * 1000003)
    pixels: list[float] = []
    for _ in range(size * size):
        value = rng.random()
        pixels.extend((value, value, value, 1.0))
    return pixels


def _update_grain_image(image: Any, size: int, seed: int, frame: int) -> None:
    pixels = _grain_pixels(size, seed, frame)
    setter = getattr(getattr(image, "pixels", None), "foreach_set", None)
    if callable(setter):
        setter(pixels)
    else:
        image.pixels = pixels
    update = getattr(image, "update", None)
    if callable(update):
        update()


def _grain_handler(scene: Any) -> None:
    try:
        import bpy

        raw = scene.get(GRAIN_CONFIG_KEY) if hasattr(scene, "get") else None
        config = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(config, dict):
            return
        image = bpy.data.images.get(str(config.get("image_name", "")))
        if image is None:
            return
        _update_grain_image(
            image,
            int(config["size"]),
            int(config["seed"]),
            int(getattr(scene, "frame_current", 1)),
        )
    except Exception:
        return


_grain_handler._dcc_mcp_photographic_post = True


def _register_grain_handler(bpy: Any) -> None:
    _remove_grain_handlers(bpy)
    handlers = getattr(getattr(bpy, "app", None), "handlers", None)
    target = getattr(handlers, "frame_change_pre", None)
    if target is None:
        raise ValueError("Blender does not expose frame_change_pre handlers")
    target.append(_grain_handler)


def _remove_grain_handlers(bpy: Any) -> None:
    handlers = getattr(getattr(bpy, "app", None), "handlers", None)
    target = getattr(handlers, "frame_change_pre", None)
    if target is None:
        raise ValueError("Blender does not expose frame_change_pre handlers")
    for handler in list(target):
        if getattr(handler, "_dcc_mcp_photographic_post", False):
            target.remove(handler)


def _ensure_grain_image(
    bpy: Any,
    size: int,
    seed: int,
    frame: int,
    image_name: str | None = None,
) -> Any:
    name = image_name or f"{POST_PREFIX}Film Grain"
    image = bpy.data.images.get(name)
    if image is not None:
        current_size = tuple(getattr(image, "size", ()))
        if current_size != (size, size):
            bpy.data.images.remove(image)
            image = None
    if image is None:
        image = bpy.data.images.new(name, width=size, height=size, alpha=False, float_buffer=True)
    colorspace = getattr(image, "colorspace_settings", None)
    if colorspace is not None and hasattr(colorspace, "name"):
        try:
            colorspace.name = "Non-Color"
        except (TypeError, ValueError):
            pass
    image["dcc_mcp_photographic_grain"] = True
    _update_grain_image(image, size, seed, frame)
    return image


def _ensure_grain_sequence(
    bpy: Any,
    scene: Any,
    directory: str,
    size: int,
    seed: int,
    sequence_name: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    if not isinstance(directory, str) or not directory.strip() or "://" in directory or "\x00" in directory:
        raise ValueError("grain_sequence_path must be a local filesystem directory")
    output_dir = Path(directory).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    start = int(getattr(scene, "frame_start", 1))
    end = int(getattr(scene, "frame_end", start))
    if end < start:
        raise ValueError("scene frame range is invalid for grain_sequence_path")
    frame_paths = []
    for frame in range(start, end + 1):
        path = output_dir / f"dcc_photo_grain_{frame:06d}.png"
        image = bpy.data.images.new(
            f"{POST_PREFIX} Grain Frame {frame}",
            width=size,
            height=size,
            alpha=False,
            float_buffer=False,
        )
        try:
            _update_grain_image(image, size, seed, frame)
            image.filepath_raw = str(path)
            image.file_format = "PNG"
            image.save()
        finally:
            bpy.data.images.remove(image)
        frame_paths.append(path)
    sequence = bpy.data.images.load(str(frame_paths[0]), check_existing=False)
    sequence.name = sequence_name or f"{POST_PREFIX}Film Grain Sequence"
    sequence.source = "SEQUENCE"
    sequence.filepath = str(output_dir / "dcc_photo_grain_######.png")
    sequence["dcc_mcp_photographic_grain"] = True
    return sequence, {
        "mode": "SEQUENCE",
        "directory": str(output_dir),
        "pattern": str(output_dir / "dcc_photo_grain_######.png"),
        "start": start,
        "end": end,
        "frame_duration": end - start + 1,
    }


def _set_scene_property(scene: Any, key: str, value: Any) -> None:
    scene[key] = value


def _scene_property(scene: Any, key: str, default: Any = None) -> Any:
    getter = getattr(scene, "get", None)
    if callable(getter):
        return getter(key, default)
    return default


def configure_photographic_post(
    scene_name: str | None = None,
    halation_threshold: float = DEFAULT_HALATION_THRESHOLD,
    halation_tint: Any = DEFAULT_HALATION_TINT,
    halation_mix: float = DEFAULT_HALATION_MIX,
    vignette_strength: float = DEFAULT_VIGNETTE_STRENGTH,
    grain_strength: float = DEFAULT_GRAIN_STRENGTH,
    grain_size: int = DEFAULT_GRAIN_SIZE,
    grain_seed: int = DEFAULT_GRAIN_SEED,
    grain_sequence_path: str | None = None,
) -> dict:
    """Create or replace the owned halation, curve, vignette and grain stack."""
    tree = None
    target = None
    source = None
    old_nodes: list[Any] = []
    candidate_nodes: list[Any] = []
    old_target_links: list[tuple[Any, Any]] = []
    old_properties: dict[str, Any] = {}
    old_handlers: list[Any] = []
    grain_image = None
    old_nodes_removed = False
    try:
        threshold = _bounded(halation_threshold, "halation_threshold", 0.0, 10.0)
        tint = _rgb(halation_tint, "halation_tint")
        mix_amount = _bounded(halation_mix, "halation_mix")
        vignette = _bounded(vignette_strength, "vignette_strength")
        grain = _bounded(grain_strength, "grain_strength")
        if isinstance(grain_size, bool) or not isinstance(grain_size, int) or not 32 <= grain_size <= 2048:
            raise ValueError("grain_size must be an integer between 32 and 2048")
        if isinstance(grain_seed, bool) or not isinstance(grain_seed, int):
            raise ValueError("grain_seed must be an integer")

        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        tree, resolved, error = _resolve_compositor_tree(
            bpy, getattr(scene, "name", scene_name), ensure=False, write=True
        )
        if error:
            ready = setup_compositor_tree(scene_name=getattr(scene, "name", scene_name), template="default")
            if not ready.get("success"):
                return ready
            tree, resolved, error = _resolve_compositor_tree(
                bpy, getattr(scene, "name", scene_name), ensure=True, write=True
            )
            if error:
                return error
        modern = modern_compositor(bpy, scene)
        output = _output_node(tree, modern)
        target = _output_target(tree, output, modern) if output is not None else None
        if output is None or target is None:
            raise ValueError("Compositor output node or Image input is unavailable")
        source = _find_base_source(tree, target, scene)
        old_nodes = _owned_nodes(tree)
        old_target_links = [
            (getattr(link, "from_socket", None), getattr(link, "to_socket", None))
            for link in list(getattr(target, "links", ()) or ())
        ]
        old_properties = {
            CONTRACT_KEY: _scene_property(scene, CONTRACT_KEY, _MISSING),
            SETTINGS_KEY: _scene_property(scene, SETTINGS_KEY, _MISSING),
            GRAIN_CONFIG_KEY: _scene_property(scene, GRAIN_CONFIG_KEY, _MISSING),
        }
        handlers = getattr(getattr(bpy, "app", None), "handlers", None)
        frame_handlers = getattr(handlers, "frame_change_pre", None)
        old_handlers = list(frame_handlers or ())
        if not grain_sequence_path and frame_handlers is None:
            raise ValueError("Blender does not expose frame_change_pre handlers")

        halation = _new_node(tree, "CompositorNodeGlare", _candidate_name(f"{POST_PREFIX}Halation"), (0.0, 260.0))
        candidate_nodes.append(halation)
        if _get_socket(halation.inputs, "Image") is None:
            raise ValueError("Glare has no Image input")
        _set_input(halation, ("Type",), "Fog Glow")
        _set_input(halation, ("Quality",), "High")
        _set_input(halation, ("Threshold", "Highlights Threshold"), threshold)
        _set_input(halation, ("Strength",), 1.0)
        _set_input(halation, ("Tint",), [*tint, 1.0])
        halation_source = _get_socket(halation.outputs, "Glare") or _get_socket(halation.outputs, "Image")

        halation_mix_node = _mix_node(tree, _candidate_name(f"{POST_PREFIX}Halation Screen"), (260.0, 260.0), "SCREEN")
        candidate_nodes.append(halation_mix_node)
        _set_input(halation_mix_node, ("Factor_Float", "Fac"), mix_amount)

        curve = _new_node(tree, "CompositorNodeCurveRGB", _candidate_name(f"{POST_PREFIX}S Curve"), (520.0, 260.0))
        candidate_nodes.append(curve)
        curve_points = _configure_curve(curve)

        ellipse = _new_node(
            tree, "CompositorNodeEllipseMask", _candidate_name(f"{POST_PREFIX}Vignette Mask"), (520.0, -80.0)
        )
        candidate_nodes.append(ellipse)
        _set_input(ellipse, ("Position",), [0.5, 0.5])
        _set_input(ellipse, ("Size",), [0.82, 0.82])
        _set_input(ellipse, ("Value",), 1.0)

        darken = _mix_node(tree, _candidate_name(f"{POST_PREFIX}Vignette Darken"), (780.0, 80.0))
        candidate_nodes.append(darken)
        _set_input(darken, ("Factor_Float", "Fac"), vignette)
        _set_input(darken, ("B_Color", "Color2"), [0.0, 0.0, 0.0, 1.0])
        vignette_mix_node = _mix_node(tree, _candidate_name(f"{POST_PREFIX}Vignette"), (1040.0, 260.0))
        candidate_nodes.append(vignette_mix_node)

        luma = _new_node(tree, "CompositorNodeRGBToBW", _candidate_name(f"{POST_PREFIX}Shadow Luma"), (780.0, -260.0))
        candidate_nodes.append(luma)
        shadow = _new_node(tree, "ShaderNodeMath", _candidate_name(f"{POST_PREFIX}Shadow Weight"), (1040.0, -260.0))
        candidate_nodes.append(shadow)
        shadow.operation = "SUBTRACT"
        _set_input(shadow, ("Value",), 1.0)
        centered = _new_node(tree, "ShaderNodeMath", _candidate_name(f"{POST_PREFIX}Grain Center"), (1040.0, -440.0))
        candidate_nodes.append(centered)
        centered.operation = "SUBTRACT"
        _set_input(centered, ("Value",), 0.5)
        if grain_sequence_path:
            grain_image, grain_sequence = _ensure_grain_sequence(
                bpy,
                scene,
                grain_sequence_path,
                grain_size,
                grain_seed,
                sequence_name=f"{POST_PREFIX}Candidate Film Grain Sequence",
            )
        else:
            grain_image = _ensure_grain_image(
                bpy,
                grain_size,
                grain_seed,
                getattr(scene, "frame_current", 1),
                image_name=f"{POST_PREFIX}Candidate Film Grain",
            )
            grain_sequence = {"mode": "HANDLER"}
        grain_texture = _new_node(
            tree, "CompositorNodeImage", _candidate_name(f"{POST_PREFIX}Film Grain Texture"), (780.0, -560.0)
        )
        candidate_nodes.append(grain_texture)
        grain_texture.image = grain_image
        if grain_sequence["mode"] == "SEQUENCE":
            grain_texture.frame_duration = grain_sequence["frame_duration"]
            grain_texture.frame_start = grain_sequence["start"]
            grain_texture.frame_offset = 0
            grain_texture.use_auto_refresh = True
        grain_bw = _new_node(
            tree, "CompositorNodeRGBToBW", _candidate_name(f"{POST_PREFIX}Film Grain Luma"), (1040.0, -560.0)
        )
        candidate_nodes.append(grain_bw)
        grain_weight = _new_node(
            tree, "ShaderNodeMath", _candidate_name(f"{POST_PREFIX}Film Grain Shadow Mix"), (1300.0, -440.0)
        )
        candidate_nodes.append(grain_weight)
        grain_weight.operation = "MULTIPLY"
        grain_color = _new_node(
            tree, "CompositorNodeCombineColor", _candidate_name(f"{POST_PREFIX}Film Grain Color"), (1560.0, -440.0)
        )
        candidate_nodes.append(grain_color)
        grain_add = _mix_node(tree, _candidate_name(f"{POST_PREFIX}Film Grain"), (1820.0, 260.0), "ADD")
        candidate_nodes.append(grain_add)
        _set_input(grain_add, ("Factor_Float", "Fac"), grain)

        _link(tree, source, _get_socket(halation.inputs, "Image"))
        _link(tree, source, _mix_socket(halation_mix_node, "a"))
        _link(tree, halation_source, _mix_socket(halation_mix_node, "b"))
        _link(tree, _mix_socket(halation_mix_node, "result"), _get_socket(curve.inputs, "Image"))
        curve_output = _image_output(curve)
        _link(tree, curve_output, _mix_socket(darken, "a"))
        _link(tree, _mix_socket(darken, "result"), _mix_socket(vignette_mix_node, "a"))
        _link(tree, curve_output, _mix_socket(vignette_mix_node, "b"))
        _link(tree, _get_socket(ellipse.outputs, "Mask"), _mix_socket(vignette_mix_node, "factor"))
        _link(tree, _mix_socket(vignette_mix_node, "result"), _get_socket(luma.inputs, "Image"))
        _link(tree, grain_texture.outputs.get("Image"), _get_socket(grain_bw.inputs, "Image"))
        _link(tree, _get_socket(grain_bw.outputs, "Val"), _get_socket(centered.inputs, "Value"))
        _link(tree, _get_socket(luma.outputs, "Val"), _get_socket(shadow.inputs, "Value_001"))
        _link(tree, _get_socket(centered.outputs, "Value"), _get_socket(grain_weight.inputs, "Value"))
        _link(tree, _get_socket(shadow.outputs, "Value"), _get_socket(grain_weight.inputs, "Value_001"))
        for channel in ("Red", "Green", "Blue"):
            _link(tree, _get_socket(grain_weight.outputs, "Value"), _get_socket(grain_color.inputs, channel))
        _link(tree, _mix_socket(vignette_mix_node, "result"), _mix_socket(grain_add, "a"))
        _link(tree, _get_socket(grain_color.outputs, "Image"), _mix_socket(grain_add, "b"))
        _link(tree, _mix_socket(grain_add, "result"), target)

        settings = {
            "halation_threshold": threshold,
            "halation_tint": tint,
            "halation_mix": mix_amount,
            "vignette_strength": vignette,
            "grain_strength": grain,
            "grain_size": grain_size,
            "grain_seed": grain_seed,
            "s_curve_points": curve_points,
            "grain_sequence_path": grain_sequence.get("directory"),
        }
        for node in old_nodes:
            _remove_node(tree, node)
        old_nodes_removed = True
        final_names = {
            halation: f"{POST_PREFIX}Halation",
            halation_mix_node: f"{POST_PREFIX}Halation Screen",
            curve: f"{POST_PREFIX}S Curve",
            ellipse: f"{POST_PREFIX}Vignette Mask",
            darken: f"{POST_PREFIX}Vignette Darken",
            vignette_mix_node: f"{POST_PREFIX}Vignette",
            luma: f"{POST_PREFIX}Shadow Luma",
            shadow: f"{POST_PREFIX}Shadow Weight",
            centered: f"{POST_PREFIX}Grain Center",
            grain_texture: f"{POST_PREFIX}Film Grain Texture",
            grain_bw: f"{POST_PREFIX}Film Grain Luma",
            grain_weight: f"{POST_PREFIX}Film Grain Shadow Mix",
            grain_color: f"{POST_PREFIX}Film Grain Color",
            grain_add: f"{POST_PREFIX}Film Grain",
        }
        for node, final_name in final_names.items():
            node.name = final_name
            node.label = final_name
        final_image_name = (
            f"{POST_PREFIX}Film Grain Sequence" if grain_sequence["mode"] == "SEQUENCE" else f"{POST_PREFIX}Film Grain"
        )
        existing_image = _collection_get(bpy.data.images, final_image_name)
        if existing_image is not None and existing_image is not grain_image:
            if getattr(existing_image, "users", 0) == 0:
                bpy.data.images.remove(existing_image)
        if _collection_get(bpy.data.images, final_image_name) is None:
            grain_image.name = final_image_name
        grain_config = {
            "image_name": grain_image.name,
            "size": grain_size,
            "seed": grain_seed,
            **grain_sequence,
        }
        _set_scene_property(scene, CONTRACT_KEY, POST_VERSION)
        _set_scene_property(scene, SETTINGS_KEY, json.dumps(settings))
        _set_scene_property(scene, GRAIN_CONFIG_KEY, json.dumps(grain_config))
        if grain_sequence["mode"] == "HANDLER":
            _register_grain_handler(bpy)
        else:
            _remove_grain_handlers(bpy)

        return skill_success(
            "Photographic post stack configured",
            node_tree_ref=resolved,
            post_version=POST_VERSION,
            removed_owned_nodes=len(old_nodes),
            nodes={
                "halation": halation.name,
                "halation_mix": halation_mix_node.name,
                "s_curve": curve.name,
                "vignette_mask": ellipse.name,
                "vignette": vignette_mix_node.name,
                "grain": grain_add.name,
            },
            settings=settings,
            grain_image=grain_image.name,
            grain_sequence=grain_config,
            prompt="Validate the photographic post stack before final animation rendering.",
        )
    except ValueError as exc:
        return skill_error("Invalid photographic post request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        rollback_errors: list[str] = []
        if tree is not None:
            try:
                if not old_nodes_removed:
                    for node in reversed(candidate_nodes):
                        if node in _iter_collection(tree.nodes):
                            _remove_node(tree, node)
                    if target is not None:
                        for link in list(getattr(target, "links", ()) or ()):
                            _remove_link(tree, link)
                        for from_socket, to_socket in old_target_links:
                            tree.links.new(from_socket, to_socket)
                    scene = getattr(getattr(bpy, "context", None), "scene", None)
                    if scene is not None:
                        for key, value in old_properties.items():
                            _restore_scene_property(scene, key, value)
                    handlers = getattr(getattr(bpy, "app", None), "handlers", None)
                    frame_handlers = getattr(handlers, "frame_change_pre", None)
                    if frame_handlers is not None:
                        frame_handlers[:] = old_handlers
                else:
                    rollback_errors.append("The previous photographic nodes were removed before the failure.")
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            return skill_exception(
                exc,
                message="Failed to configure photographic post stack; rollback failed",
                prompt="Inspect the compositor tree before retrying: " + "; ".join(rollback_errors),
            )
        return skill_exception(exc, message="Failed to configure photographic post stack")


def _values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=1e-6, abs_tol=1e-6)
    if isinstance(expected, (list, tuple)):
        try:
            actual_values = list(actual)
        except (TypeError, ValueError):
            return False
        return len(actual_values) == len(expected) and all(
            _values_equal(item, value) for item, value in zip(actual_values, expected)
        )
    return actual == expected


def _curve_points(node: Any) -> list[list[float]]:
    mapping = getattr(node, "mapping", None)
    curves = getattr(mapping, "curves", None)
    if curves is None or len(curves) == 0:
        return []
    points = []
    for point in getattr(curves[-1], "points", ()):
        co = getattr(point, "location", None)
        if co is None:
            co = getattr(point, "co", None)
        if co is None:
            continue
        try:
            points.append([float(co.x if hasattr(co, "x") else co[0]), float(co.y if hasattr(co, "y") else co[1])])
        except (AttributeError, IndexError, TypeError, ValueError):
            continue
    return points


def validate_photographic_post(scene_name: str | None = None) -> dict:
    """Validate the owned compositor stack and frame-changing grain handler."""
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        issues: list[dict[str, Any]] = []
        if _scene_property(scene, CONTRACT_KEY) != POST_VERSION:
            issues.append({"code": "PHOTO_POST_CONTRACT_MISSING", "severity": "error"})
        tree, resolved, tree_error = _resolve_compositor_tree(
            bpy, getattr(scene, "name", scene_name), ensure=False, write=False
        )
        if tree_error:
            return tree_error
        modern = modern_compositor(bpy, scene)
        output = _output_node(tree, modern)
        target = _output_target(tree, output, modern) if output is not None else None
        required = {
            "halation": f"{POST_PREFIX}Halation",
            "halation_mix": f"{POST_PREFIX}Halation Screen",
            "s_curve": f"{POST_PREFIX}S Curve",
            "vignette_mask": f"{POST_PREFIX}Vignette Mask",
            "vignette_darken": f"{POST_PREFIX}Vignette Darken",
            "vignette": f"{POST_PREFIX}Vignette",
            "shadow_luma": f"{POST_PREFIX}Shadow Luma",
            "shadow_weight": f"{POST_PREFIX}Shadow Weight",
            "grain_texture": f"{POST_PREFIX}Film Grain Texture",
            "grain_luma": f"{POST_PREFIX}Film Grain Luma",
            "grain_shadow_mix": f"{POST_PREFIX}Film Grain Shadow Mix",
            "grain_center": f"{POST_PREFIX}Grain Center",
            "grain_color": f"{POST_PREFIX}Film Grain Color",
            "grain": f"{POST_PREFIX}Film Grain",
        }
        nodes = {key: _collection_get(tree.nodes, name) for key, name in required.items()}
        for key, node in nodes.items():
            if node is None:
                issues.append({"code": "PHOTO_POST_NODE_MISSING", "severity": "error", "field": key})
        if target is None or not getattr(target, "is_linked", False):
            issues.append({"code": "PHOTO_POST_OUTPUT_UNLINKED", "severity": "error"})
        raw_settings = _scene_property(scene, SETTINGS_KEY)
        settings = json.loads(raw_settings) if isinstance(raw_settings, str) else raw_settings or {}

        def check_input(
            node_key: str,
            socket_names: tuple[str, ...],
            expected: Any,
            code: str,
            field: str,
        ) -> None:
            node = nodes.get(node_key)
            if node is None:
                return
            socket = _get_socket(getattr(node, "inputs", ()), socket_names[0])
            if socket is None:
                socket = next(
                    (_get_socket(getattr(node, "inputs", ()), name) for name in socket_names[1:]),
                    None,
                )
            actual = getattr(socket, "default_value", None) if socket is not None else None
            if isinstance(expected, (list, tuple)):
                try:
                    actual = list(actual)[: len(expected)]
                except (TypeError, ValueError):
                    pass
            if field in {"halation_type", "halation_quality"}:
                matches = str(actual).strip().replace("_", " ").casefold() == str(expected).strip().casefold()
            else:
                matches = _values_equal(actual, expected)
            if not matches:
                issues.append(
                    {
                        "code": code,
                        "severity": "error",
                        "field": field,
                        "expected": expected,
                        "actual": actual,
                    }
                )

        halation = nodes.get("halation")
        if halation is not None:
            threshold_socket = _get_socket(halation.inputs, "Threshold") or _get_socket(
                halation.inputs, "Highlights Threshold"
            )
            if not _values_equal(getattr(threshold_socket, "default_value", None), settings.get("halation_threshold")):
                issues.append({"code": "PHOTO_POST_HALATION_THRESHOLD", "severity": "error"})
            check_input("halation", ("Type",), "Fog Glow", "PHOTO_POST_HALATION_TYPE", "halation_type")
            check_input("halation", ("Quality",), "High", "PHOTO_POST_HALATION_QUALITY", "halation_quality")
            tint = settings.get("halation_tint")
            if isinstance(tint, (list, tuple)):
                check_input("halation", ("Tint",), list(tint), "PHOTO_POST_HALATION_TINT", "halation_tint")
        check_input(
            "halation_mix",
            ("Factor_Float", "Fac"),
            settings.get("halation_mix"),
            "PHOTO_POST_HALATION_MIX",
            "halation_mix",
        )
        curve = nodes.get("s_curve")
        expected_curve_points = settings.get("s_curve_points")
        if curve is not None and isinstance(expected_curve_points, list):
            actual_curve_points = _curve_points(curve)
            if not all(
                any(_values_equal(actual, expected) for actual in actual_curve_points)
                for expected in expected_curve_points
            ):
                issues.append(
                    {
                        "code": "PHOTO_POST_S_CURVE_MISMATCH",
                        "severity": "error",
                        "field": "s_curve_points",
                        "expected": expected_curve_points,
                        "actual": actual_curve_points,
                    }
                )
        check_input(
            "vignette_mask",
            ("Position",),
            [0.5, 0.5],
            "PHOTO_POST_VIGNETTE_POSITION",
            "vignette_position",
        )
        check_input(
            "vignette_mask",
            ("Size",),
            [0.82, 0.82],
            "PHOTO_POST_VIGNETTE_SIZE",
            "vignette_size",
        )
        check_input(
            "vignette_darken",
            ("Factor_Float", "Fac"),
            settings.get("vignette_strength"),
            "PHOTO_POST_VIGNETTE_STRENGTH",
            "vignette_strength",
        )
        check_input(
            "grain",
            ("Factor_Float", "Fac"),
            settings.get("grain_strength"),
            "PHOTO_POST_GRAIN_STRENGTH",
            "grain_strength",
        )

        def check_operation(node_key: str, expected: str, code: str, field: str) -> None:
            node = nodes.get(node_key)
            if node is not None and getattr(node, "operation", None) != expected:
                issues.append(
                    {
                        "code": code,
                        "severity": "error",
                        "field": field,
                        "expected": expected,
                        "actual": getattr(node, "operation", None),
                    }
                )

        def check_unlinked(node_key: str, socket_names: tuple[str, ...], code: str, field: str) -> None:
            node = nodes.get(node_key)
            if node is None:
                return
            socket = next(
                (_get_socket(getattr(node, "inputs", ()), name) for name in socket_names),
                None,
            )
            if socket is not None and getattr(socket, "links", ()):
                issues.append(
                    {
                        "code": code,
                        "severity": "error",
                        "field": field,
                        "expected": "unlinked input",
                        "actual": "linked input",
                    }
                )

        def check_link_from(
            node_key: str,
            input_names: tuple[str, ...],
            source_key: str,
            source_names: tuple[str, ...],
            code: str,
            field: str,
        ) -> None:
            node = nodes.get(node_key)
            source = nodes.get(source_key)
            if node is None or source is None:
                return

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
                left_name = getattr(left, "name", None)
                right_name = getattr(right, "name", None)
                if isinstance(left_name, str) and isinstance(right_name, str):
                    return left_name == right_name
                try:
                    return left == right
                except (TypeError, ValueError, RuntimeError):
                    return False

            target = next(
                (_get_socket(getattr(node, "inputs", ()), name) for name in input_names),
                None,
            )
            matching_link = (
                any(
                    same_node(getattr(link, "from_node", None), source)
                    and (
                        getattr(getattr(link, "from_socket", None), "name", None) in source_names
                        or getattr(getattr(link, "from_socket", None), "identifier", None) in source_names
                    )
                    for link in getattr(target, "links", ())
                )
                if target is not None
                else False
            )
            if not matching_link:
                issues.append(
                    {
                        "code": code,
                        "severity": "error",
                        "field": field,
                        "expected": f"linked from {source_key} ({', '.join(source_names)})",
                        "actual": "different or missing source",
                    }
                )

        check_input(
            "vignette_darken",
            ("B_Color", "Color2"),
            [0.0, 0.0, 0.0, 1.0],
            "PHOTO_POST_VIGNETTE_COLOR",
            "vignette_color",
        )
        check_unlinked("vignette_darken", ("B_Color", "Color2"), "PHOTO_POST_VIGNETTE_COLOR_LINK", "vignette_color")
        check_operation("shadow_weight", "SUBTRACT", "PHOTO_POST_SHADOW_WEIGHT_OPERATION", "shadow_weight_operation")
        check_operation("grain_shadow_mix", "MULTIPLY", "PHOTO_POST_GRAIN_WEIGHT_OPERATION", "grain_weight_operation")
        check_operation("grain_center", "SUBTRACT", "PHOTO_POST_GRAIN_CENTER_OPERATION", "grain_center_operation")
        check_link_from(
            "shadow_weight",
            ("Value_001", "Value 2"),
            "shadow_luma",
            ("Val",),
            "PHOTO_POST_SHADOW_LINK",
            "shadow_weight_luma",
        )
        check_link_from(
            "grain_shadow_mix",
            ("Value_001", "Value 2"),
            "shadow_weight",
            ("Value",),
            "PHOTO_POST_GRAIN_SHADOW_LINK",
            "grain_shadow_luma",
        )
        for channel in ("Red", "Green", "Blue"):
            check_link_from(
                "grain_color",
                (channel,),
                "grain_shadow_mix",
                ("Value",),
                "PHOTO_POST_GRAIN_COLOR_LINK",
                f"grain_color_{channel.lower()}",
            )
        grain_config = _scene_property(scene, GRAIN_CONFIG_KEY)
        config = json.loads(grain_config) if isinstance(grain_config, str) else grain_config or {}
        image = bpy.data.images.get(str(config.get("image_name", ""))) if config else None
        if image is None:
            issues.append({"code": "PHOTO_POST_GRAIN_IMAGE_MISSING", "severity": "error"})
        elif tuple(getattr(image, "size", ())) != (config.get("size"), config.get("size")):
            issues.append(
                {
                    "code": "PHOTO_POST_GRAIN_SIZE_MISMATCH",
                    "severity": "error",
                    "field": "grain_size",
                    "expected": [config.get("size"), config.get("size")],
                    "actual": list(getattr(image, "size", ())),
                }
            )
        texture = nodes.get("grain_texture")
        if texture is not None and image is not None:
            texture_image = getattr(texture, "image", None)
            if getattr(texture_image, "name", None) != getattr(image, "name", None):
                issues.append(
                    {
                        "code": "PHOTO_POST_GRAIN_TEXTURE_MISMATCH",
                        "severity": "error",
                        "field": "grain_texture",
                        "expected": getattr(image, "name", None),
                        "actual": getattr(texture_image, "name", None),
                    }
                )
        handlers = getattr(getattr(bpy, "app", None), "handlers", None)
        frame_handlers = getattr(handlers, "frame_change_pre", ()) if handlers is not None else ()
        if config.get("mode") == "SEQUENCE":
            if image is None or getattr(image, "source", None) != "SEQUENCE":
                issues.append({"code": "PHOTO_POST_GRAIN_SEQUENCE_MISSING", "severity": "error"})
            if texture is None or not getattr(texture, "use_auto_refresh", False):
                issues.append({"code": "PHOTO_POST_GRAIN_SEQUENCE_REFRESH", "severity": "error"})
        elif config and not any(getattr(item, "_dcc_mcp_photographic_post", False) for item in frame_handlers):
            issues.append({"code": "PHOTO_POST_GRAIN_HANDLER_MISSING", "severity": "error"})
        return skill_success(
            "Photographic post validation completed",
            node_tree_ref=resolved,
            valid=not issues,
            issues=issues,
            settings=settings,
            grain=config,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return skill_error("Invalid photographic post state", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate photographic post stack")
