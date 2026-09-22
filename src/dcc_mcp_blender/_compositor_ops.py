"""Blender compositor node tree operations.

`blender-node-graph` exposes read-only compositor introspection. This module
closes the write gap: it enables the compositor, builds a starter tree, and
creates, connects, disconnects, and sets values on compositor nodes.

All helpers degrade to structured errors when ``bpy`` is unavailable so the
module stays importable outside Blender.
"""

from __future__ import annotations

from typing import Any, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

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
    # Accept any compositor node id even when it is missing from the catalogue.
    if key.startswith("compositornode") and len(key) > len("compositornode"):
        return str(node_type).strip()
    return None


def list_compositor_node_types(category: str | None = None, search: str | None = None) -> dict:
    """List the compositor node type catalogue used by ``create_compositor_node``.

    The catalogue is static and not filtered by Blender version, so an entry may
    still fail to instantiate on an older Blender; ``create_compositor_node``
    surfaces that as a version-aware error.

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
    for node_id, label, entry_category, aliases in _COMPOSITOR_NODE_CATALOG:
        if wanted and _normalise_key(entry_category) != wanted:
            continue
        haystack = " ".join((node_id, label, entry_category, *aliases)).lower()
        if needle and needle not in haystack:
            continue
        node_types.append(
            {
                "id": node_id,
                "label": label,
                "category": entry_category,
                "aliases": list(aliases),
            }
        )
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


def _resolve_compositor_tree(bpy: Any, scene_name: str | None, *, ensure: bool = False) -> tuple:
    """Resolve ``scene.node_tree``, optionally enabling compositor nodes first."""
    scene, error = _resolve_scene(bpy, scene_name)
    if error:
        return None, {}, error
    if not getattr(scene, "use_nodes", False):
        if not ensure:
            return (
                None,
                {},
                skill_error(
                    "Compositor nodes not enabled",
                    "Run setup_compositor_tree (or set_compositor_enabled) to enable scene.use_nodes.",
                ),
            )
        scene.use_nodes = True
    node_tree = getattr(scene, "node_tree", None)
    if node_tree is None:
        return (
            None,
            {},
            skill_error(
                "No compositor node tree",
                "The scene has no compositor node tree even though use_nodes is enabled.",
            ),
        )
    return node_tree, _scene_ref(scene), None


def _ensure_compositor_node(node_tree: Any, node_type: str, preferred_name: str) -> tuple:
    """Return an existing node of *node_type* or create one named *preferred_name*.

    A node that merely carries *preferred_name* does not qualify: an unrelated
    node renamed to "Composite" must not be mistaken for the composite output
    node. The preferred name is only applied when it is still free, so Blender's
    own de-duplication ("Composite.001") survives.
    """
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
    """Enable or disable compositor nodes for a scene."""
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        scene.use_nodes = bool(enabled)
        node_tree = getattr(scene, "node_tree", None)
        node_count = len(_iter_collection(getattr(node_tree, "nodes", []))) if node_tree is not None else 0
        return skill_success(
            f"{'Enabled' if enabled else 'Disabled'} compositor nodes for {getattr(scene, 'name', scene_name)}",
            scene_name=getattr(scene, "name", scene_name),
            use_nodes=bool(enabled),
            node_count=node_count,
            prompt="Use setup_compositor_tree to build a starter graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to toggle compositor nodes")


def setup_compositor_tree(scene_name: str | None = None, template: str = "default", clear: bool = False) -> dict:
    """Enable compositor nodes and optionally build a starter node tree.

    Args:
        scene_name: Target scene; defaults to the active scene.
        template: ``default`` wires Render Layers -> Composite, ``empty`` only
            enables the compositor.
        clear: Remove every existing node before applying the template.
    """
    wanted = str(template or "default").lower()
    if wanted not in _VALID_TEMPLATES:
        return skill_error(
            f"Unsupported compositor template: {template}",
            f"Available templates: {', '.join(_VALID_TEMPLATES)}",
        )
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        scene.use_nodes = True
        node_tree = getattr(scene, "node_tree", None)
        if node_tree is None:
            return skill_error("No compositor node tree", "The scene has no compositor node tree.")

        removed = 0
        if clear:
            for node in list(_iter_collection(node_tree.nodes)):
                _remove_node(node_tree, node)
                removed += 1

        created: list = []
        link = None
        if wanted == "default":
            render_layers, made_rl = _ensure_compositor_node(node_tree, _R_LAYERS_NODE, "Render Layers")
            composite, made_comp = _ensure_compositor_node(node_tree, _COMPOSITE_NODE, "Composite")
            if made_rl:
                created.append(getattr(render_layers, "name", "Render Layers"))
            if made_comp:
                created.append(getattr(composite, "name", "Composite"))
            source = _get_socket(render_layers.outputs, "Image")
            target = _get_socket(composite.inputs, "Image")
            if source is None or target is None:
                return skill_error(
                    "Could not wire the default compositor tree",
                    "The Render Layers or Composite node has no Image socket in this Blender version.",
                )
            if not _existing_link(
                node_tree,
                getattr(render_layers, "name", ""),
                "Image",
                getattr(composite, "name", ""),
                "Image",
            ):
                link = _link_info(node_tree.links.new(source, target))

        return skill_success(
            f"Compositor tree ready for {getattr(scene, 'name', scene_name)} ({wanted} template)",
            scene_name=getattr(scene, "name", scene_name),
            template=wanted,
            use_nodes=True,
            cleared_nodes=removed,
            created_nodes=created,
            node_count=len(_iter_collection(node_tree.nodes)),
            link=link,
            prompt="Use create_compositor_node, connect_compositor_nodes, and set_compositor_node_value.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set up the compositor tree")


def clear_compositor_tree(scene_name: str | None = None) -> dict:
    """Remove every node (and therefore every link) from the compositor tree."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name)
        if error:
            return error
        removed = 0
        for node in list(_iter_collection(node_tree.nodes)):
            _remove_node(node_tree, node)
            removed += 1
        return skill_success(
            f"Cleared compositor tree for {resolved.get('scene_name')}",
            node_tree_ref=resolved,
            removed_nodes=removed,
            prompt="Use create_compositor_node to rebuild the graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
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
    node_location = None
    if location is not None:
        if isinstance(location, (str, bytes)) or len(location) != 2:
            return skill_error("Invalid location", "location must be [x, y].")
        node_location = (float(location[0]), float(location[1]))
    try:
        import bpy

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name, ensure=True)
        if error:
            return error
        if name and _collection_get(node_tree.nodes, str(name)) is not None:
            return skill_error(f"Node already exists: {name}", "Choose a unique node name.")
        node = _create_node_in_tree(node_tree, resolved_type)
        if name:
            node.name = str(name)
            node.label = str(name)
        if node_location is not None:
            node.location = node_location
        return skill_success(
            f"Created compositor node {getattr(node, 'name', resolved_type)}",
            node_tree_ref=resolved,
            node_type=resolved_type,
            node=_node_info(node),
            prompt="Use connect_compositor_nodes or set_compositor_node_value next.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(
            exc,
            message=f"Failed to create compositor node {node_type}",
            prompt=(
                f"Blender rejected {resolved_type}; this node type may not exist in the running "
                "Blender version. Use list_compositor_node_types to pick an alternative."
            ),
        )


def delete_compositor_node(node_name: str, scene_name: str | None = None) -> dict:
    """Delete a node from the compositor tree."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name)
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

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name, ensure=True)
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

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name)
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

        node_tree, resolved, error = _resolve_compositor_tree(bpy, scene_name, ensure=True)
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
