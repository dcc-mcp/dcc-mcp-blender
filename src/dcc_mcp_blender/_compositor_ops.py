"""Blender compositor node tree operations.

`blender-node-graph` exposes read-only compositor introspection. This module
closes the write gap: it enables the compositor, builds a starter tree, and
creates, connects, disconnects, and sets values on compositor nodes.

All helpers degrade to structured errors when ``bpy`` is unavailable so the
module stays importable outside Blender.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._compositor_compat import (
    compositor_enabled,
    compositor_tree,
    modern_compositor,
    require_local_scene,
    require_single_user_tree,
    set_compositor_state,
)
from dcc_mcp_blender._node_graph_ops import (
    _collection_get,
    _create_node_in_tree,
    _get_socket,
    _iter_collection,
    _link_info,
    _node_info,
    _node_type,
    _remove_link,
    _remove_node,
    _set_socket_value,
    _socket_info,
    _socket_names,
    _socket_value,
)

# Curated compositor node catalogue: (blender id, label, category, aliases).
# The catalogue drives alias resolution for `create_compositor_node` and feeds
# `list_compositor_node_types`, so agents can discover ids without guessing.
_COMPOSITOR_NODE_CATALOG = (
    # --- Input -------------------------------------------------------------
    ("CompositorNodeRLayers", "Render Layers", "input", ("render layers", "rlayers", "renderlayer")),
    ("CompositorNodeImage", "Image", "input", ("image", "picture", "still")),
    ("CompositorNodeTexture", "Texture", "input", ("texture",)),
    ("CompositorNodeValue", "Value", "input", ("value", "float", "scalar")),
    ("CompositorNodeRGB", "RGB", "input", ("rgb", "color", "colour")),
    ("CompositorNodeTime", "Time", "input", ("time", "frame curve")),
    ("CompositorNodeTrackPos", "Track Position", "input", ("track position", "tracking")),
    ("CompositorNodeSceneTime", "Scene Time", "input", ("scene time",)),
    ("CompositorNodeBokehImage", "Bokeh Image", "input", ("bokeh image",)),
    # --- Output ------------------------------------------------------------
    ("CompositorNodeComposite", "Composite", "output", ("composite", "output", "final")),
    ("CompositorNodeViewer", "Viewer", "output", ("viewer", "backdrop", "preview")),
    ("CompositorNodeOutputFile", "File Output", "output", ("file output", "fileoutput", "write", "save")),
    ("CompositorNodeSplitViewer", "Split Viewer", "output", ("split viewer",)),
    ("CompositorNodeLevels", "Levels", "output", ("levels",)),
    # --- Color -------------------------------------------------------------
    ("CompositorNodeBrightContrast", "Brightness/Contrast", "color", ("bright contrast", "brightness", "contrast")),
    ("CompositorNodeGamma", "Gamma", "color", ("gamma",)),
    ("CompositorNodeHueSat", "Hue/Saturation/Value", "color", ("hue sat", "hsv", "saturation")),
    ("CompositorNodeInvert", "Invert", "color", ("invert", "negative")),
    ("CompositorNodeExposure", "Exposure", "color", ("exposure", "ev")),
    ("CompositorNodeColorBalance", "Color Balance", "color", ("color balance", "lift gamma gain", "white balance")),
    ("CompositorNodeTonemap", "Tonemap", "color", ("tonemap", "tone map", "hdr")),
    ("CompositorNodeCurveRGB", "RGB Curves", "color", ("rgb curves", "curves", "color curve")),
    ("CompositorNodeCurveVec", "Vector Curves", "color", ("vector curves", "vec curves")),
    ("CompositorNodeHueCorrect", "Hue Correct", "color", ("hue correct",)),
    ("CompositorNodePosterize", "Posterize", "color", ("posterize",)),
    ("CompositorNodePremulKey", "Premultiply Alpha", "color", ("premul key", "premultiply")),
    ("CompositorNodeConvertColorSpace", "Convert Colorspace", "color", ("convert colorspace", "colorspace")),
    ("CompositorNodeSeparateColor", "Separate Color", "color", ("separate color", "split color")),
    ("CompositorNodeCombineColor", "Combine Color", "color", ("combine color", "merge color")),
    # --- Filter ------------------------------------------------------------
    ("CompositorNodeBlur", "Blur", "filter", ("blur", "gaussian")),
    ("CompositorNodeBokehBlur", "Bokeh Blur", "filter", ("bokeh blur", "dof blur")),
    ("CompositorNodeVecBlur", "Vector Blur", "filter", ("vector blur", "motion blur")),
    ("CompositorNodeDefocus", "Defocus", "filter", ("defocus", "depth of field", "dof")),
    ("CompositorNodeDilateErode", "Dilate/Erode", "filter", ("dilate erode", "erode", "dilate")),
    ("CompositorNodeFilter", "Filter", "filter", ("filter", "soften", "sharpen", "laplace")),
    ("CompositorNodeGlare", "Glare", "filter", ("glare", "bloom", "streaks", "ghost")),
    ("CompositorNodeBilateralBlur", "Bilateral Blur", "filter", ("bilateral blur",)),
    ("CompositorNodeDenoise", "Denoise", "filter", ("denoise", "denoising", "optix", "oidn")),
    ("CompositorNodeDespeckle", "Despeckle", "filter", ("despeckle",)),
    ("CompositorNodeDisplace", "Displace", "filter", ("displace",)),
    ("CompositorNodeInpaint", "Inpaint", "filter", ("inpaint",)),
    ("CompositorNodeKuwahara", "Kuwahara", "filter", ("kuwahara", "painterly")),
    ("CompositorNodePixelate", "Pixelate", "filter", ("pixelate", "mosaic")),
    ("CompositorNodeSunBeams", "Sun Beams", "filter", ("sun beams", "god rays")),
    # --- Matte -------------------------------------------------------------
    ("CompositorNodeKeying", "Keying", "matte", ("keying", "green screen", "chroma key")),
    ("CompositorNodeChromaMatte", "Chroma Key", "matte", ("chroma matte", "chroma key")),
    ("CompositorNodeColorMatte", "Color Key", "matte", ("color matte", "color key")),
    ("CompositorNodeChannelMatte", "Channel Key", "matte", ("channel matte", "channel key")),
    ("CompositorNodeDiffMatte", "Difference Key", "matte", ("diff matte", "difference key")),
    ("CompositorNodeDistanceMatte", "Distance Key", "matte", ("distance matte", "distance key")),
    ("CompositorNodeLumaMatte", "Luminance Key", "matte", ("luma matte", "luminance key")),
    ("CompositorNodeCryptomatte", "Cryptomatte", "matte", ("cryptomatte", "crypto")),
    ("CompositorNodeCryptomatteV2", "Cryptomatte V2", "matte", ("cryptomatte v2", "crypto v2")),
    # --- Converter ---------------------------------------------------------
    ("CompositorNodeAlphaOver", "Alpha Over", "converter", ("alpha over", "over", "composite over")),
    ("CompositorNodeCombineXYZ", "Combine XYZ", "converter", ("combine xyz",)),
    ("CompositorNodeSeparateXYZ", "Separate XYZ", "converter", ("separate xyz",)),
    ("CompositorNodeCombineRGBA", "Combine RGBA", "converter", ("combine rgba",)),
    ("CompositorNodeSeparateRGBA", "Separate RGBA", "converter", ("separate rgba",)),
    ("CompositorNodeMapRange", "Map Range", "converter", ("map range", "remap")),
    ("CompositorNodeMapValue", "Map Value", "converter", ("map value",)),
    ("CompositorNodeMath", "Math", "converter", ("math", "add", "multiply", "subtract")),
    ("CompositorNodeMixRGB", "Mix Color", "converter", ("mix rgb", "mix color", "mix", "blend")),
    ("CompositorNodeRGBToBW", "RGB to BW", "converter", ("rgb to bw", "grayscale", "desaturate")),
    ("CompositorNodeSetAlpha", "Set Alpha", "converter", ("set alpha",)),
    ("CompositorNodeSwitch", "Switch", "converter", ("switch",)),
    ("CompositorNodeSwitchView", "Switch View", "converter", ("switch view", "stereo")),
    ("CompositorNodeValToRGB", "Color Ramp", "converter", ("val to rgb", "color ramp", "ramp")),
    ("CompositorNodeZcombine", "Z Combine", "converter", ("z combine", "zcombine", "depth combine")),
    # --- Vector ------------------------------------------------------------
    ("CompositorNodeNormal", "Normal", "vector", ("normal", "normal pass")),
    ("CompositorNodeNormalize", "Normalize", "vector", ("normalize",)),
    ("CompositorNodeTransform", "Transform", "vector", ("transform",)),
    ("CompositorNodeTranslate", "Translate", "vector", ("translate", "offset")),
    ("CompositorNodeRotate", "Rotate", "vector", ("rotate", "rotation")),
    ("CompositorNodeScale", "Scale", "vector", ("scale", "resize")),
    ("CompositorNodeCrop", "Crop", "vector", ("crop", "trim")),
    ("CompositorNodeBoxMask", "Box Mask", "vector", ("box mask", "rectangle mask")),
    ("CompositorNodeEllipseMask", "Ellipse Mask", "vector", ("ellipse mask", "circle mask")),
    ("CompositorNodeCornerPin", "Corner Pin", "vector", ("corner pin",)),
    ("CompositorNodeSplit", "Split", "vector", ("split", "wipe")),
    ("CompositorNodeIDMask", "ID Mask", "vector", ("id mask", "object index")),
    ("CompositorNodeDoubleEdgeMask", "Double Edge Mask", "vector", ("double edge mask",)),
    ("CompositorNodeStabilize2D", "Stabilize 2D", "vector", ("stabilize 2d", "stabilize")),
    # --- Group -------------------------------------------------------------
    ("CompositorNodeGroup", "Group", "group", ("group", "node group")),
)

_R_LAYERS_NODE = "CompositorNodeRLayers"
_COMPOSITE_NODE = "CompositorNodeComposite"
_VALID_TEMPLATES = ("default", "empty")


def _normalise_key(value: str) -> str:
    """Fold a node type or alias into a lookup key."""
    return "".join(char for char in str(value).lower() if char.isalnum())


def _build_alias_index() -> dict:
    """Map every alias, label, and Blender id to its canonical node id."""
    index: dict = {}
    for node_id, label, _category, aliases in _COMPOSITOR_NODE_CATALOG:
        for key in (node_id, label, *aliases):
            index[_normalise_key(key)] = node_id
    return index


_NODE_TYPE_ALIASES = _build_alias_index()


def _node_catalog_categories() -> list:
    """Return the catalogue categories in declaration order."""
    categories: list = []
    for _node_id, _label, category, _aliases in _COMPOSITOR_NODE_CATALOG:
        if category not in categories:
            categories.append(category)
    return categories


_NODE_CATEGORIES = _node_catalog_categories()


def resolve_compositor_node_type(node_type: str) -> str | None:
    """Resolve a Blender id, label, or alias to a canonical compositor node id.

    Args:
        node_type: Blender id (``CompositorNodeDenoise``), label (``Denoise``),
            or one of the catalogue aliases (``denoise``).

    Returns:
        The canonical Blender node id, or ``None`` when unknown.
    """
    key = _normalise_key(node_type)
    if not key:
        return None
    if key in _NODE_TYPE_ALIASES:
        return _NODE_TYPE_ALIASES[key]
    # Accept only the unified ShaderNode ids derived from this compositor
    # catalogue, not arbitrary shader-only nodes (for example TexImage).
    unified = {"ShaderNode" + item[0][len("CompositorNode") :] for item in _COMPOSITOR_NODE_CATALOG}
    for current_id in unified | {"NodeGroupOutput"}:
        if key == _normalise_key(current_id):
            return current_id
    # Preserve support for compositor ids absent from the curated catalogue.
    if key.startswith("compositornode") and len(key) > len("compositornode"):
        return str(node_type).strip()
    return None


def list_compositor_node_types(category: str | None = None, search: str | None = None) -> dict:
    """List the compositor node type catalogue used by ``create_compositor_node``.

    Native RNA availability and known replacement ids are included when a host
    is available. A registered type still needs to support the target tree;
    creation validates that without publishing an unsuccessful new group.

    Args:
        category: Optional category filter, for example ``filter`` or ``matte``.
        search: Optional case-insensitive substring match on id, label, or alias.
    """
    wanted = _normalise_key(category) if category else None
    if wanted and wanted not in [_normalise_key(item) for item in _NODE_CATEGORIES]:
        return skill_error(
            f"Unknown compositor node category: {category}",
            f"Available categories: {', '.join(_NODE_CATEGORIES)}",
        )
    needle = str(search).lower() if search else None
    node_types = []
    host = None
    try:
        import bpy

        host = bpy
    except ImportError:
        pass
    if host is not None:
        try:
            modern_compositor(host, host.context.scene)
        except ValueError as exc:
            return skill_error(str(exc), "Use a supported Blender compositor API.")
    for node_id, label, entry_category, aliases in _COMPOSITOR_NODE_CATALOG:
        if wanted and _normalise_key(entry_category) != wanted:
            continue
        resolved_id = _host_node_type(host, host.context.scene, node_id) if host is not None else node_id
        haystack = " ".join((node_id, resolved_id, label, entry_category, *aliases)).lower()
        if needle and needle not in haystack:
            continue
        native_types = getattr(host, "types", None) if host is not None else None
        entry = {
            "id": resolved_id,
            "label": label,
            "category": entry_category,
            "aliases": list(aliases),
        }
        if resolved_id != node_id:
            entry["legacy_id"] = node_id
        if native_types is not None:
            entry["registered"] = getattr(native_types, resolved_id, None) is not None
        node_types.append(entry)
    return skill_success(
        f"Found {len(node_types)} compositor node type(s)",
        category=category,
        search=search,
        categories=list(_NODE_CATEGORIES),
        node_types=node_types,
        count=len(node_types),
        prompt="Pass the id (or any alias) to create_compositor_node.",
    )


def _resolve_scene(bpy: Any, scene_name: str | None) -> tuple:
    """Resolve a scene by name, falling back to the active scene."""
    if scene_name:
        scene = _collection_get(bpy.data.scenes, str(scene_name))
        if scene is None:
            return None, skill_error(f"Scene not found: {scene_name}", f"No scene named '{scene_name}'.")
        return scene, None
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return None, skill_error("No active scene", "bpy.context.scene is unavailable.")
    return scene, None


def _scene_ref(scene: Any) -> dict:
    """Build the ``node_tree_ref`` payload reported for compositor operations."""
    return {"kind": "compositor", "scene_name": getattr(scene, "name", None)}


def _resolve_compositor_tree(bpy: Any, scene_name: str | None, *, ensure: bool = False, write: bool = False) -> tuple:
    """Resolve a tree without enabling modern render output as a read side effect."""
    scene, error = _resolve_scene(bpy, scene_name)
    if error:
        return None, {}, error
    modern = modern_compositor(bpy, scene)
    if not modern and not compositor_enabled(bpy, scene):
        if not ensure:
            return (
                None,
                {},
                skill_error("Compositor nodes not enabled", "Run setup_compositor_tree to enable compositing."),
            )
        set_compositor_state(bpy, scene, True)
    node_tree = compositor_tree(bpy, scene)
    if node_tree is None:
        return None, {}, skill_error("No compositor node tree", "Run setup_compositor_tree first.")
    if write:
        require_local_scene(scene)
        if modern:
            require_single_user_tree(node_tree)
    return node_tree, _scene_ref(scene), None


def _host_node_type(bpy: Any, scene: Any, node_type: str) -> str:
    if not modern_compositor(bpy, scene):
        return node_type
    if node_type == "CompositorNodeComposite":
        return "NodeGroupOutput"
    if node_type == "CompositorNodeMath":
        return "ShaderNodeMath"
    # Unified nodes keep their suffix. Only offer the replacement when native
    # RNA says it exists and the former id does not; creation still validates
    # whether the type is allowed in this particular compositor tree.
    types = getattr(bpy, "types", None)
    if types is not None and node_type.startswith("CompositorNode"):
        replacement = "ShaderNode" + node_type[len("CompositorNode") :]
        if getattr(types, node_type, None) is None and getattr(types, replacement, None) is not None:
            return replacement
    return node_type


def _ensure_output_socket(tree: Any) -> None:
    outputs = [item for item in tree.interface.items_tree if getattr(item, "in_out", None) == "OUTPUT"]
    if outputs:
        if getattr(outputs[0], "socket_type", None) != "NodeSocketColor":
            raise ValueError(
                "The first compositor group output must be a Color socket; existing interface was not changed"
            )
    else:
        tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")


def _group_output_input(tree: Any, node: Any) -> Any:
    outputs = [item for item in tree.interface.items_tree if getattr(item, "in_out", None) == "OUTPUT"]
    return _get_socket(node.inputs, outputs[0].identifier) or _get_socket(node.inputs, outputs[0].name)


def _discard_group(bpy: Any, tree: Any) -> None:
    bpy.data.node_groups.remove(tree)


def _ensure_compositor_node(node_tree: Any, node_type: str, preferred_name: str) -> tuple:
    """Return an existing node of *node_type* or create one named *preferred_name*.

    A node that merely carries *preferred_name* does not qualify: an unrelated
    node renamed to "Composite" must not be mistaken for the composite output
    node. The preferred name is only applied when it is still free, so Blender's
    own de-duplication ("Composite.001") survives.
    """
    if node_type == "NodeGroupOutput":
        for candidate in _iter_collection(node_tree.nodes):
            if _node_type(candidate) == node_type and getattr(candidate, "is_active_output", False):
                return candidate, False
    existing = _collection_get(node_tree.nodes, preferred_name)
    if existing is not None and _node_type(existing) == node_type:
        return existing, False
    for candidate in _iter_collection(node_tree.nodes):
        if _node_type(candidate) == node_type:
            return candidate, False
    node = _create_node_in_tree(node_tree, node_type)
    if _collection_get(node_tree.nodes, preferred_name) is None:
        try:
            node.name = preferred_name
            node.label = preferred_name
        except Exception:  # pragma: no cover - read-only node name in exotic trees
            pass
    if not getattr(node, "label", None):
        # Keep the node labelled even when the preferred name was taken, so the
        # graph never renders as a row of unnamed boxes.
        try:
            node.label = getattr(node, "name", "") or preferred_name
        except Exception:  # pragma: no cover - read-only label in exotic trees
            pass
    return node, True


def _existing_link(node_tree: Any, from_node: str, from_socket: str, to_node: str, to_socket: str) -> bool:
    """Return True when the tree already links the given endpoints."""
    for link in _iter_collection(node_tree.links):
        info = _link_info(link)
        if (
            info["from_node"] == from_node
            and info["to_node"] == to_node
            and from_socket in {info["from_socket"], info["from_socket_identifier"]}
            and to_socket in {info["to_socket"], info["to_socket_identifier"]}
        ):
            return True
    return False


def set_compositor_enabled(scene_name: str | None = None, enabled: bool = True) -> dict:
    """Toggle actual render compositing, preserving the existing node group."""
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        set_compositor_state(bpy, scene, bool(enabled))
        node_tree = compositor_tree(bpy, scene)
        actual = compositor_enabled(bpy, scene)
        return skill_success(
            f"{'Enabled' if actual else 'Disabled'} compositor nodes for {getattr(scene, 'name', scene_name)}",
            scene_name=getattr(scene, "name", scene_name),
            use_nodes=actual,
            enabled=actual,
            node_count=len(_iter_collection(getattr(node_tree, "nodes", []))) if node_tree is not None else 0,
            prompt="Use setup_compositor_tree to build a starter graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to toggle compositor nodes")


def setup_compositor_tree(scene_name: str | None = None, template: str = "default", clear: bool = False) -> dict:
    """Build Render Layers -> native output; publish new 5.x groups only on success."""
    wanted = str(template or "default").lower()
    if wanted not in _VALID_TEMPLATES:
        return skill_error(
            f"Unsupported compositor template: {template}", f"Available templates: {', '.join(_VALID_TEMPLATES)}"
        )
    owned_tree = None
    scene = None
    previous_tree = None
    before_nodes = before_sockets = before_links = None
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        modern = modern_compositor(bpy, scene)
        require_local_scene(scene)
        was_enabled = compositor_enabled(bpy, scene)
        previous_tree = compositor_tree(bpy, scene)
        if modern and previous_tree is not None and not clear:
            require_single_user_tree(previous_tree)
        removed = len(_iter_collection(previous_tree.nodes)) if clear and previous_tree is not None else 0
        if modern and (previous_tree is None or clear):
            # A clear operation must not delete nodes from another scene sharing
            # the same group. Keep the old datablock intact; replace this binding.
            owned_tree = bpy.data.node_groups.new(f"{scene.name} Compositor", "CompositorNodeTree")
            node_tree = owned_tree
        else:
            if not modern:
                set_compositor_state(bpy, scene, True)
            node_tree = compositor_tree(bpy, scene)
        if node_tree is None:
            raise ValueError("The scene has no compositor node tree")
        before_nodes = list(node_tree.nodes)
        before_sockets = list(node_tree.interface.items_tree) if modern else []
        before_links = [
            (link.from_socket, link.to_socket, getattr(link, "is_muted", False)) for link in node_tree.links
        ]
        # Preflight an existing output interface before any destructive work.
        if modern and wanted == "default":
            _ensure_output_socket(node_tree)
        if clear and not modern:
            for node in list(node_tree.nodes):
                _remove_node(node_tree, node)
        created = []
        link = None
        if wanted == "default":
            output_type = "NodeGroupOutput" if modern else _COMPOSITE_NODE
            render_layers, made_rl = _ensure_compositor_node(node_tree, _R_LAYERS_NODE, "Render Layers")
            composite, made_comp = _ensure_compositor_node(node_tree, output_type, "Composite")
            if made_rl:
                render_layers.scene = scene
                created.append(render_layers.name)
            if made_comp:
                created.append(composite.name)
            source = _get_socket(render_layers.outputs, "Image")
            target = _group_output_input(node_tree, composite) if modern else _get_socket(composite.inputs, "Image")
            if source is None or target is None:
                raise ValueError("The native render/output nodes have no compatible Image sockets")
            if not any(item.from_socket == source and item.to_socket == target for item in node_tree.links):
                link = _link_info(node_tree.links.new(source, target))
        if owned_tree is not None:
            scene.compositing_node_group = owned_tree
        set_compositor_state(bpy, scene, True)
        return skill_success(
            f"Compositor tree ready for {scene.name} ({wanted} template)",
            scene_name=scene.name,
            template=wanted,
            use_nodes=compositor_enabled(bpy, scene),
            cleared_nodes=removed,
            created_nodes=created,
            node_count=len(_iter_collection(node_tree.nodes)),
            link=link,
            tree_name=getattr(node_tree, "name", None),
            prompt="Use create_compositor_node, connect_compositor_nodes, and set_compositor_node_value.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        # Owned groups were staged; restoring the binding removes all changes.
        # Non-clearing additions to an existing tree can also be rolled back.
        try:
            if owned_tree is not None:
                try:
                    if scene.compositing_node_group == owned_tree:
                        scene.compositing_node_group = previous_tree
                finally:
                    _discard_group(bpy, owned_tree)
            elif before_nodes is not None and not clear:
                for item in list(node_tree.nodes):
                    if item not in before_nodes:
                        _remove_node(node_tree, item)
                # Keep untouched native links (and their mute state/identity).
                # links.new may replace an existing single-input connection;
                # only recreate those original links that actually disappeared.
                endpoints = [(source, target) for source, target, _muted in before_links]
                for item in list(node_tree.links):
                    if (item.from_socket, item.to_socket) not in endpoints:
                        _remove_link(node_tree, item)
                for source, target, muted in before_links:
                    if not any(item.from_socket == source and item.to_socket == target for item in node_tree.links):
                        restored = node_tree.links.new(source, target)
                        if hasattr(restored, "is_muted"):
                            restored.is_muted = muted
                if modern:
                    for item in list(node_tree.interface.items_tree):
                        if item not in before_sockets:
                            node_tree.interface.remove(item)
            if scene is not None and "was_enabled" in locals():
                set_compositor_state(bpy, scene, was_enabled)
        except Exception as rollback_error:
            return skill_exception(
                exc,
                message="Failed to set up compositor; rollback failed",
                prompt=f"Inspect before retrying: {rollback_error}",
            )
        return skill_exception(exc, message="Failed to set up the compositor tree")


def clear_compositor_tree(scene_name: str | None = None) -> dict:
    """Clear this scene, without destroying another scene's shared 5.x group."""
    replacement = None
    previous = None
    scene = None
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name)
        if error:
            return error
        require_local_scene(scene)
        removed = len(_iter_collection(node_tree.nodes))
        if modern_compositor(bpy, scene):
            previous = node_tree
            replacement = bpy.data.node_groups.new(f"{scene.name} Compositor", "CompositorNodeTree")
            scene.compositing_node_group = replacement
            if scene.compositing_node_group != replacement:
                raise ValueError("Blender did not retain the cleared compositor group")
        else:
            for node in list(_iter_collection(node_tree.nodes)):
                _remove_node(node_tree, node)
        return skill_success(
            f"Cleared compositor tree for {resolved.get('scene_name')}",
            node_tree_ref=resolved,
            removed_nodes=removed,
            prompt="Use create_compositor_node to rebuild the graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        if replacement is not None:
            try:
                try:
                    if scene.compositing_node_group == replacement:
                        scene.compositing_node_group = previous
                finally:
                    _discard_group(bpy, replacement)
            except Exception as rollback_error:
                return skill_exception(
                    exc,
                    message="Failed to clear compositor; rollback failed",
                    prompt=f"Inspect before retrying: {rollback_error}",
                )
        return skill_exception(exc, message="Failed to clear the compositor tree")


def create_compositor_node(
    node_type: str,
    name: str | None = None,
    location: Sequence[float] | None = None,
    scene_name: str | None = None,
) -> dict:
    """Create a compositor node in the scene's compositor tree."""
    resolved_type = resolve_compositor_node_type(node_type)
    if resolved_type is None:
        return skill_error(
            f"Unsupported compositor node type: {node_type}",
            "Use list_compositor_node_types to discover valid ids, labels, and aliases.",
        )
    # Validate before touching Blender so a rejected payload cannot leave an
    # orphan node behind or flip scene.use_nodes for an operation that failed.
    # The try/except keeps a non-sequence or non-numeric payload on the same
    # actionable skill_error instead of leaking a Python traceback.
    node_location = None
    if location is not None:
        try:
            if isinstance(location, (str, bytes)) or len(location) != 2:
                return skill_error("Invalid location", "location must be [x, y].")
            node_location = (float(location[0]), float(location[1]))
            if not all(math.isfinite(value) for value in node_location):
                return skill_error("Invalid location", "location values must be finite.")
        except (TypeError, ValueError, KeyError, OverflowError):
            return skill_error("Invalid location", "location must be [x, y].")
    owned_tree = None
    node = None
    node_tree = None
    original_sockets = None
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        modern = modern_compositor(bpy, scene)
        require_local_scene(scene)
        resolved_type = _host_node_type(bpy, scene, resolved_type)
        node_tree = compositor_tree(bpy, scene)
        if modern and node_tree is None:
            owned_tree = bpy.data.node_groups.new(f"{scene.name} Compositor", "CompositorNodeTree")
            node_tree = owned_tree
        elif modern:
            require_single_user_tree(node_tree)
        elif not modern:
            node_tree, _resolved, error = _resolve_compositor_tree(bpy, scene_name, ensure=True)
            if error:
                return error
        if name and _collection_get(node_tree.nodes, str(name)) is not None:
            return skill_error(f"Node already exists: {name}", "Choose a unique node name.")
        original_sockets = list(node_tree.interface.items_tree) if modern else []
        if modern and resolved_type == "NodeGroupOutput":
            _ensure_output_socket(node_tree)
        node = _create_node_in_tree(node_tree, resolved_type)
        if resolved_type == _R_LAYERS_NODE:
            node.scene = scene
        if name:
            node.name = str(name)
            node.label = str(name)
        if node_location is not None:
            node.location = node_location
        record = _node_info(node)
        if owned_tree is not None:
            scene.compositing_node_group = owned_tree
        return skill_success(
            f"Created compositor node {getattr(node, 'name', resolved_type)}",
            node_tree_ref=_scene_ref(scene),
            node_type=resolved_type,
            node=record,
            prompt="Use connect_compositor_nodes or set_compositor_node_value next.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        try:
            if owned_tree is not None:
                try:
                    if scene.compositing_node_group == owned_tree:
                        scene.compositing_node_group = None
                finally:
                    _discard_group(bpy, owned_tree)
            elif node_tree is not None:
                if node is not None:
                    _remove_node(node_tree, node)
                if original_sockets is not None and modern:
                    for item in list(node_tree.interface.items_tree):
                        if item not in original_sockets:
                            node_tree.interface.remove(item)
        except Exception as rollback_error:
            return skill_exception(
                exc,
                message="Failed to create compositor node; rollback failed",
                prompt=f"Inspect before retrying: {rollback_error}",
            )
        return skill_exception(
            exc,
            message=f"Failed to create compositor node {node_type}",
            prompt=f"Blender rejected {resolved_type}; this type may be unavailable in this Blender version.",
        )


def delete_compositor_node(node_name: str, scene_name: str | None = None) -> dict:
    """Delete a node from the compositor tree."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name, write=True)
        if error:
            return error
        node = _collection_get(node_tree.nodes, str(node_name))
        if node is None:
            return skill_error(f"Node not found: {node_name}", f"No compositor node named '{node_name}'.")
        _remove_node(node_tree, node)
        return skill_success(
            f"Deleted compositor node {node_name}",
            node_tree_ref=resolved,
            node_name=node_name,
            node_count=len(_iter_collection(node_tree.nodes)),
            prompt="Use list_compositor_nodes or list_compositor_node_links to verify the graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to delete compositor node {node_name}")


def connect_compositor_nodes(
    from_node: str,
    from_socket: str,
    to_node: str,
    to_socket: str,
    scene_name: str | None = None,
) -> dict:
    """Connect an output socket to an input socket in the compositor tree."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name, ensure=True, write=True)
        if error:
            return error
        source_node = _collection_get(node_tree.nodes, str(from_node))
        target_node = _collection_get(node_tree.nodes, str(to_node))
        if source_node is None:
            return skill_error(f"Node not found: {from_node}", f"No compositor node named '{from_node}'.")
        if target_node is None:
            return skill_error(f"Node not found: {to_node}", f"No compositor node named '{to_node}'.")
        source = _get_socket(source_node.outputs, str(from_socket))
        target = _get_socket(target_node.inputs, str(to_socket))
        if source is None:
            return skill_error(
                f"Output socket not found: {from_socket}",
                f"Available outputs: {', '.join(_socket_names(source_node.outputs))}",
            )
        if target is None:
            return skill_error(
                f"Input socket not found: {to_socket}",
                f"Available inputs: {', '.join(_socket_names(target_node.inputs))}",
            )
        link = _link_info(node_tree.links.new(source, target))
        return skill_success(
            f"Connected {from_node}.{from_socket} to {to_node}.{to_socket}",
            node_tree_ref=resolved,
            link=link,
            prompt="Use list_compositor_node_links to inspect graph connectivity.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to connect compositor nodes")


def disconnect_compositor_nodes(
    scene_name: str | None = None,
    link_id: str | None = None,
    from_node: str | None = None,
    from_socket: str | None = None,
    to_node: str | None = None,
    to_socket: str | None = None,
) -> dict:
    """Disconnect compositor links by id or by endpoint fields."""
    if not any([link_id, from_node, from_socket, to_node, to_socket]):
        return skill_error(
            "No disconnect criteria",
            "Provide link_id or at least one endpoint field (from_node, from_socket, to_node, to_socket).",
        )
    try:
        import bpy

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name, write=True)
        if error:
            return error
        removed = []
        for link in list(_iter_collection(node_tree.links)):
            info = _link_info(link)
            matches_id = bool(link_id) and info["id"] == str(link_id)
            matches_endpoints = all(
                [
                    from_node is None or info["from_node"] == str(from_node),
                    from_socket is None or str(from_socket) in {info["from_socket"], info["from_socket_identifier"]},
                    to_node is None or info["to_node"] == str(to_node),
                    to_socket is None or str(to_socket) in {info["to_socket"], info["to_socket_identifier"]},
                ]
            )
            if matches_id or (not link_id and matches_endpoints):
                _remove_link(node_tree, link)
                removed.append(info)
        if not removed:
            return skill_error("No matching compositor links", "No link matched the provided id or endpoints.")
        return skill_success(
            f"Disconnected {len(removed)} compositor link(s)",
            node_tree_ref=resolved,
            removed_links=removed,
            count=len(removed),
            prompt="Use list_compositor_node_links to verify the graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to disconnect compositor nodes")


def set_compositor_node_value(
    node_name: str,
    socket: str,
    value: Any,
    scene_name: str | None = None,
) -> dict:
    """Set an input socket default value on a compositor node."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name, ensure=True, write=True)
        if error:
            return error
        node = _collection_get(node_tree.nodes, str(node_name))
        if node is None:
            return skill_error(f"Node not found: {node_name}", f"No compositor node named '{node_name}'.")
        target = _get_socket(node.inputs, str(socket))
        if target is None:
            return skill_error(
                f"Input socket not found: {socket}",
                f"Available inputs: {', '.join(_socket_names(node.inputs))}",
            )
        normalized = _set_socket_value(target, value)
        return skill_success(
            f"Set {socket} on {node_name}",
            node_tree_ref=resolved,
            node_name=node_name,
            socket=socket,
            value=normalized,
            is_linked=bool(getattr(target, "is_linked", False)),
            prompt="Linked sockets ignore default values; use disconnect_compositor_nodes to unlink first.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set {socket} on {node_name}")


def get_compositor_node_value(
    node_name: str,
    socket: str | None = None,
    scene_name: str | None = None,
) -> dict:
    """Read one socket value or every socket value for a compositor node."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name)
        if error:
            return error
        node = _collection_get(node_tree.nodes, str(node_name))
        if node is None:
            return skill_error(f"Node not found: {node_name}", f"No compositor node named '{node_name}'.")
        if socket:
            target = _get_socket(node.inputs, str(socket)) or _get_socket(node.outputs, str(socket))
            if target is None:
                return skill_error(f"Socket not found: {socket}", "The node has no matching input or output socket.")
            return skill_success(
                f"Read {socket} on {node_name}",
                node_tree_ref=resolved,
                node_name=node_name,
                socket=_socket_info(target),
                value=_socket_value(target),
                prompt="Use set_compositor_node_value for mutable input sockets.",
            )
        return skill_success(
            f"Read socket values for {node_name}",
            node_tree_ref=resolved,
            node_name=node_name,
            inputs=[_socket_info(item) for item in _iter_collection(node.inputs)],
            outputs=[_socket_info(item) for item in _iter_collection(node.outputs)],
            prompt="Use list_compositor_node_types before adding nodes to the graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to read socket values for {node_name}")


def list_compositor_node_links(scene_name: str | None = None) -> dict:
    """List every link in the compositor tree."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name)
        if error:
            return error
        links = [_link_info(link) for link in _iter_collection(node_tree.links)]
        return skill_success(
            f"Found {len(links)} compositor link(s)",
            node_tree_ref=resolved,
            links=links,
            count=len(links),
            prompt="Use disconnect_compositor_nodes with a link id or endpoints to remove a link.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list compositor node links")
