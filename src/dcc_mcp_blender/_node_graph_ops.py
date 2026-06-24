"""Shared Blender shader and geometry node graph operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_SHADER_KINDS = {"shader", "material"}
_GEOMETRY_KINDS = {"geometry", "geometry_nodes", "node_group"}
_MODIFIER_KINDS = {"geometry_modifier", "modifier"}
_COMPOSITOR_KINDS = {"compositor", "composite"}


def _iter_collection(collection: Any) -> list[Any]:
    try:
        return list(collection)
    except TypeError:
        return []


def _collection_get(collection: Any, name: str) -> Any | None:
    getter = getattr(collection, "get", None)
    if callable(getter):
        return getter(name)
    for item in _iter_collection(collection):
        if getattr(item, "name", None) == name:
            return item
    return None


def _node_type(node: Any) -> str | None:
    return getattr(node, "bl_idname", None) or getattr(node, "type", None)


def _socket_name(socket: Any) -> str:
    return str(getattr(socket, "name", socket))


def _socket_identifier(socket: Any) -> str:
    return str(getattr(socket, "identifier", None) or _socket_name(socket))


def _socket_value(socket: Any) -> Any:
    if not hasattr(socket, "default_value"):
        return None
    value = socket.default_value
    if isinstance(value, tuple):
        return list(value)
    try:
        if not isinstance(value, (str, bytes, int, float, bool, dict, list, type(None))):
            return list(value)
    except TypeError:
        pass
    return value


def _socket_info(socket: Any) -> dict[str, Any]:
    return {
        "name": _socket_name(socket),
        "identifier": _socket_identifier(socket),
        "type": getattr(socket, "type", None),
        "value": _socket_value(socket),
        "is_linked": bool(getattr(socket, "is_linked", False)),
    }


def _socket_items(sockets: Any) -> list[Any]:
    if hasattr(sockets, "values"):
        try:
            return list(sockets.values())
        except Exception:
            pass
    return _iter_collection(sockets)


def _socket_names(sockets: Any) -> list[str]:
    if hasattr(sockets, "keys"):
        try:
            return [str(name) for name in sockets.keys()]
        except Exception:
            pass
    return [_socket_name(socket) for socket in _socket_items(sockets)]


def _get_socket(sockets: Any, name: str) -> Any | None:
    getter = getattr(sockets, "get", None)
    if callable(getter):
        socket = getter(name)
        if socket is not None:
            return socket
    for socket in _socket_items(sockets):
        if _socket_name(socket) == name or _socket_identifier(socket) == name:
            return socket
    return None


def _node_info(node: Any, include_sockets: bool = True) -> dict[str, Any]:
    info = {
        "name": getattr(node, "name", None),
        "type": getattr(node, "type", None),
        "bl_idname": getattr(node, "bl_idname", None),
        "label": getattr(node, "label", ""),
        "location": list(getattr(node, "location", []) or []),
    }
    if include_sockets:
        info["inputs"] = [_socket_info(socket) for socket in _socket_items(getattr(node, "inputs", []))]
        info["outputs"] = [_socket_info(socket) for socket in _socket_items(getattr(node, "outputs", []))]
    return info


def _normalise_value(default_value: Any, value: Any) -> Any:
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return value
    try:
        target_len = len(default_value)
    except TypeError:
        return value
    if target_len == 4 and len(value) == 3:
        return [*value, 1.0]
    return value


def _set_socket_value(socket: Any, value: Any) -> Any:
    if not hasattr(socket, "default_value"):
        raise ValueError(f"Socket {_socket_name(socket)} does not expose a default value")
    socket.default_value = _normalise_value(socket.default_value, value)
    return _socket_value(socket)


def _link_id(link: Any) -> str:
    from_node = getattr(getattr(link, "from_node", None), "name", "")
    from_socket = _socket_identifier(getattr(link, "from_socket", ""))
    to_node = getattr(getattr(link, "to_node", None), "name", "")
    to_socket = _socket_identifier(getattr(link, "to_socket", ""))
    return f"{from_node}:{from_socket}->{to_node}:{to_socket}"


def _link_info(link: Any) -> dict[str, Any]:
    return {
        "id": _link_id(link),
        "from_node": getattr(getattr(link, "from_node", None), "name", None),
        "from_socket": _socket_name(getattr(link, "from_socket", "")),
        "from_socket_identifier": _socket_identifier(getattr(link, "from_socket", "")),
        "to_node": getattr(getattr(link, "to_node", None), "name", None),
        "to_socket": _socket_name(getattr(link, "to_socket", "")),
        "to_socket_identifier": _socket_identifier(getattr(link, "to_socket", "")),
    }


def _ensure_mapping(value: Mapping[str, Any] | None, label: str) -> tuple[dict[str, Any] | None, dict | None]:
    if value is None:
        return {}, None
    if not isinstance(value, Mapping):
        return None, skill_error(f"Invalid {label}", f"{label} must be an object.")
    return dict(value), None


def _get_material(bpy: Any, material_name: str, *, create: bool = False) -> Any | None:
    material = _collection_get(bpy.data.materials, material_name)
    if material is None and create:
        material = bpy.data.materials.new(material_name)
    return material


def _ensure_material_nodes(material: Any) -> Any:
    material.use_nodes = True
    return material.node_tree


def _get_geometry_modifier(obj: Any, modifier_name: str | None = None) -> Any | None:
    for modifier in _iter_collection(getattr(obj, "modifiers", [])):
        if getattr(modifier, "type", None) != "NODES":
            continue
        if modifier_name is None or getattr(modifier, "name", None) == modifier_name:
            return modifier
    return None


def _new_modifier(obj: Any, name: str = "Geometry Nodes") -> Any:
    return obj.modifiers.new(name=name, type="NODES")


def _resolve_node_tree(bpy: Any, node_tree_ref: Mapping[str, Any]) -> tuple[Any | None, dict[str, Any], dict | None]:
    if not isinstance(node_tree_ref, Mapping):
        return None, {}, skill_error("Invalid node_tree_ref", "node_tree_ref must be an object.")
    kind = str(node_tree_ref.get("kind") or node_tree_ref.get("type") or "").lower()
    if not kind:
        return None, {}, skill_error("Invalid node_tree_ref", "node_tree_ref.kind is required.")

    if kind in _SHADER_KINDS:
        material_name = (
            node_tree_ref.get("material_name") or node_tree_ref.get("owner_name") or node_tree_ref.get("name")
        )
        if not material_name:
            return None, {}, skill_error("Invalid node_tree_ref", "material_name is required for shader node trees.")
        material = _get_material(bpy, str(material_name))
        if material is None:
            return (
                None,
                {},
                skill_error(f"Material not found: {material_name}", f"No material named '{material_name}'."),
            )
        if not getattr(material, "use_nodes", False) or getattr(material, "node_tree", None) is None:
            return (
                None,
                {},
                skill_error(
                    f"Material {material_name} does not use nodes",
                    "Enable material nodes or use create_material_with_nodes first.",
                ),
            )
        return material.node_tree, {"kind": "shader", "material_name": str(material_name)}, None

    if kind in _GEOMETRY_KINDS:
        group_name = node_tree_ref.get("group_name") or node_tree_ref.get("owner_name") or node_tree_ref.get("name")
        if not group_name:
            return None, {}, skill_error("Invalid node_tree_ref", "group_name is required for geometry node groups.")
        group = _collection_get(bpy.data.node_groups, str(group_name))
        if group is None:
            return None, {}, skill_error(f"Node group not found: {group_name}", f"No node group named '{group_name}'.")
        return group, {"kind": "geometry", "group_name": str(group_name)}, None

    if kind in _COMPOSITOR_KINDS:
        scene = bpy.context.scene
        if not getattr(scene, "use_nodes", False) or getattr(scene, "node_tree", None) is None:
            return (
                None,
                {},
                skill_error(
                    "Compositor nodes not enabled",
                    "Enable compositor nodes (scene.use_nodes = True) before accessing the node tree.",
                ),
            )
        return scene.node_tree, {"kind": "compositor"}, None

    if kind in _MODIFIER_KINDS:
        object_name = node_tree_ref.get("object_name") or node_tree_ref.get("owner_name")
        if not object_name:
            return None, {}, skill_error("Invalid node_tree_ref", "object_name is required for modifier node trees.")
        obj = _collection_get(bpy.data.objects, str(object_name))
        if obj is None:
            return None, {}, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier = _get_geometry_modifier(obj, node_tree_ref.get("modifier_name"))
        if modifier is None:
            return (
                None,
                {},
                skill_error(
                    f"Geometry Nodes modifier not found on {object_name}",
                    "Add or assign a Geometry Nodes modifier first.",
                ),
            )
        group = getattr(modifier, "node_group", None)
        if group is None:
            return (
                None,
                {},
                skill_error(
                    f"Modifier {modifier.name} has no node group",
                    "Assign a Geometry Nodes node group before editing its graph.",
                ),
            )
        return (
            group,
            {
                "kind": "geometry_modifier",
                "object_name": str(object_name),
                "modifier_name": modifier.name,
                "group_name": getattr(group, "name", None),
            },
            None,
        )

    return None, {}, skill_error("Unsupported node tree kind", f"Unsupported node_tree_ref.kind: {kind}")


def _create_node_in_tree(node_tree: Any, node_type: str) -> Any:
    try:
        return node_tree.nodes.new(type=node_type)
    except TypeError:
        return node_tree.nodes.new(node_type)


def _remove_node(node_tree: Any, node: Any) -> None:
    remover = getattr(node_tree.nodes, "remove", None)
    if callable(remover):
        remover(node)


def _remove_link(node_tree: Any, link: Any) -> None:
    remover = getattr(node_tree.links, "remove", None)
    if callable(remover):
        remover(link)


def _find_principled_node(nodes: Any, node_name: str = "Principled BSDF") -> Any | None:
    node = _collection_get(nodes, node_name)
    if node is not None:
        return node
    for candidate in _iter_collection(nodes):
        if (
            getattr(candidate, "type", None) == "BSDF_PRINCIPLED"
            or getattr(candidate, "bl_idname", None) == "ShaderNodeBsdfPrincipled"
        ):
            return candidate
    return None


def _node_group_type(group: Any) -> str | None:
    return getattr(group, "bl_idname", None) or getattr(group, "type", None)


def _interface_sockets(group: Any) -> list[Any]:
    interface = getattr(group, "interface", None)
    items_tree = getattr(interface, "items_tree", None)
    if items_tree is not None:
        return [item for item in _iter_collection(items_tree) if hasattr(item, "name")]
    inputs = _iter_collection(getattr(group, "inputs", []))
    outputs = _iter_collection(getattr(group, "outputs", []))
    return inputs + outputs


def _modifier_get(modifier: Any, key: str) -> Any:
    getter = getattr(modifier, "get", None)
    if callable(getter):
        return getter(key)
    try:
        return modifier[key]
    except Exception:
        return None


def _modifier_set(modifier: Any, key: str, value: Any) -> None:
    try:
        modifier[key] = value
    except TypeError:
        setattr(modifier, key, value)


def _modifier_input_identifier(group: Any, input_name: str) -> str:
    for socket in _interface_sockets(group):
        if getattr(socket, "in_out", "INPUT") not in {"INPUT", None}:
            continue
        if getattr(socket, "name", None) == input_name or getattr(socket, "identifier", None) == input_name:
            return _socket_identifier(socket)
    return input_name


def _add_group_socket(group: Any, name: str, socket_type: str, in_out: str) -> None:
    for socket in _interface_sockets(group):
        if getattr(socket, "name", None) == name and getattr(socket, "in_out", in_out) == in_out:
            return
    interface = getattr(group, "interface", None)
    if interface is not None and callable(getattr(interface, "new_socket", None)):
        try:
            interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
            return
        except Exception:
            pass
    items_tree = getattr(interface, "items_tree", None)
    if items_tree is not None and callable(getattr(items_tree, "new_socket", None)):
        try:
            items_tree.new_socket(name=name, in_out=in_out, socket_type=socket_type)
            return
        except Exception:
            pass
    collection = getattr(group, "inputs" if in_out == "INPUT" else "outputs", None)
    if collection is not None and callable(getattr(collection, "new", None)):
        try:
            collection.new(socket_type, name)
        except Exception:
            pass


def _ensure_group_node(group: Any, node_type: str, names: set[str]) -> None:
    for node in _iter_collection(getattr(group, "nodes", [])):
        if getattr(node, "bl_idname", None) == node_type or getattr(node, "type", None) == node_type:
            return
        if getattr(node, "name", None) in names:
            return
    try:
        group.nodes.new(type=node_type)
    except Exception:
        pass


def _create_passthrough_geometry_group(group: Any) -> None:
    _add_group_socket(group, "Geometry", "NodeSocketGeometry", "INPUT")
    _add_group_socket(group, "Geometry", "NodeSocketGeometry", "OUTPUT")
    _ensure_group_node(group, "NodeGroupInput", {"Group Input"})
    _ensure_group_node(group, "NodeGroupOutput", {"Group Output"})


def list_node_trees(kind: str, owner_name: str | None = None) -> dict:
    """List material or geometry node trees."""
    try:
        import bpy

        key = kind.lower()
        trees = []
        if key in _SHADER_KINDS or key == "all":
            for material in _iter_collection(bpy.data.materials):
                if owner_name and material.name != owner_name:
                    continue
                if getattr(material, "use_nodes", False) and getattr(material, "node_tree", None) is not None:
                    trees.append(
                        {
                            "kind": "shader",
                            "owner_name": material.name,
                            "node_tree_name": getattr(material.node_tree, "name", None),
                            "node_count": len(_iter_collection(material.node_tree.nodes)),
                        }
                    )
        if key in _GEOMETRY_KINDS or key == "all":
            for group in _iter_collection(bpy.data.node_groups):
                if owner_name and group.name != owner_name:
                    continue
                if _node_group_type(group) in {"GeometryNodeTree", "GEOMETRY"}:
                    trees.append(
                        {
                            "kind": "geometry",
                            "owner_name": group.name,
                            "node_tree_name": group.name,
                            "node_count": len(_iter_collection(group.nodes)),
                        }
                    )
        return skill_success(
            f"Found {len(trees)} node tree(s)",
            kind=kind,
            owner_name=owner_name,
            node_trees=trees,
            count=len(trees),
            prompt="Use list_nodes with a node_tree_ref to inspect a specific graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list node trees")


def list_nodes(node_tree_ref: Mapping[str, Any], type_filter: str | None = None) -> dict:
    """List nodes in a resolved node tree."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_node_tree(bpy, node_tree_ref)
        if error:
            return error
        nodes = []
        for node in _iter_collection(node_tree.nodes):
            if type_filter and type_filter not in {str(getattr(node, "type", "")), str(getattr(node, "bl_idname", ""))}:
                continue
            nodes.append(_node_info(node))
        return skill_success(
            f"Found {len(nodes)} node(s)",
            node_tree_ref=resolved,
            type_filter=type_filter,
            nodes=nodes,
            count=len(nodes),
            prompt="Use list_node_sockets before connecting or setting node values.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list nodes")


def create_node(
    node_tree_ref: Mapping[str, Any],
    node_type: str,
    name: str | None = None,
    location: Sequence[float] | None = None,
) -> dict:
    """Create a node in a material or geometry node tree."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_node_tree(bpy, node_tree_ref)
        if error:
            return error
        if name and _collection_get(node_tree.nodes, name) is not None:
            return skill_error(f"Node already exists: {name}", "Choose a unique node name.")
        node = _create_node_in_tree(node_tree, node_type)
        if name:
            node.name = name
            node.label = name
        if location is not None:
            if isinstance(location, (str, bytes)) or len(location) != 2:
                return skill_error("Invalid location", "location must be [x, y].")
            node.location = (float(location[0]), float(location[1]))
        return skill_success(
            f"Created node {getattr(node, 'name', node_type)}",
            node_tree_ref=resolved,
            node=_node_info(node),
            prompt="Use connect_nodes or set_node_input to wire the node into the graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create node {node_type}")


def delete_node(node_tree_ref: Mapping[str, Any], node_name: str) -> dict:
    """Delete a node from a node tree."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_node_tree(bpy, node_tree_ref)
        if error:
            return error
        node = _collection_get(node_tree.nodes, node_name)
        if node is None:
            return skill_error(f"Node not found: {node_name}", f"No node named '{node_name}'.")
        _remove_node(node_tree, node)
        return skill_success(
            f"Deleted node {node_name}",
            node_tree_ref=resolved,
            node_name=node_name,
            prompt="Use list_nodes or list_node_links to inspect the remaining graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to delete node {node_name}")


def list_node_sockets(node_tree_ref: Mapping[str, Any], node_name: str) -> dict:
    """List sockets on a node."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_node_tree(bpy, node_tree_ref)
        if error:
            return error
        node = _collection_get(node_tree.nodes, node_name)
        if node is None:
            return skill_error(f"Node not found: {node_name}", f"No node named '{node_name}'.")
        return skill_success(
            f"Listed sockets for {node_name}",
            node_tree_ref=resolved,
            node_name=node_name,
            inputs=[_socket_info(socket) for socket in _socket_items(node.inputs)],
            outputs=[_socket_info(socket) for socket in _socket_items(node.outputs)],
            prompt="Use connect_nodes with socket names or identifiers.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to list sockets for {node_name}")


def list_node_links(node_tree_ref: Mapping[str, Any]) -> dict:
    """List node links in a graph."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_node_tree(bpy, node_tree_ref)
        if error:
            return error
        links = [_link_info(link) for link in _iter_collection(node_tree.links)]
        return skill_success(
            f"Found {len(links)} node link(s)",
            node_tree_ref=resolved,
            links=links,
            count=len(links),
            prompt="Use disconnect_nodes with a link id or endpoints to remove a link.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list node links")


def connect_nodes(
    node_tree_ref: Mapping[str, Any],
    from_node: str,
    from_socket: str,
    to_node: str,
    to_socket: str,
) -> dict:
    """Connect two node sockets."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_node_tree(bpy, node_tree_ref)
        if error:
            return error
        source = _collection_get(node_tree.nodes, from_node)
        target = _collection_get(node_tree.nodes, to_node)
        if source is None:
            return skill_error(f"Node not found: {from_node}", f"No source node named '{from_node}'.")
        if target is None:
            return skill_error(f"Node not found: {to_node}", f"No target node named '{to_node}'.")
        source_socket = _get_socket(source.outputs, from_socket)
        target_socket = _get_socket(target.inputs, to_socket)
        if source_socket is None:
            return skill_error(
                f"Output socket not found: {from_socket}",
                f"Available outputs: {', '.join(_socket_names(source.outputs))}",
            )
        if target_socket is None:
            return skill_error(
                f"Input socket not found: {to_socket}", f"Available inputs: {', '.join(_socket_names(target.inputs))}"
            )
        link = node_tree.links.new(source_socket, target_socket)
        return skill_success(
            f"Connected {from_node}.{from_socket} to {to_node}.{to_socket}",
            node_tree_ref=resolved,
            link=_link_info(link),
            prompt="Use list_node_links to inspect graph connectivity.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to connect node sockets")


def disconnect_nodes(
    node_tree_ref: Mapping[str, Any],
    link_id: str | None = None,
    from_node: str | None = None,
    from_socket: str | None = None,
    to_node: str | None = None,
    to_socket: str | None = None,
) -> dict:
    """Disconnect node links by id or endpoint tuple."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_node_tree(bpy, node_tree_ref)
        if error:
            return error
        removed = []
        for link in list(_iter_collection(node_tree.links)):
            info = _link_info(link)
            matches_id = link_id and info["id"] == link_id
            matches_endpoints = all(
                [
                    from_node is None or info["from_node"] == from_node,
                    from_socket is None or from_socket in {info["from_socket"], info["from_socket_identifier"]},
                    to_node is None or info["to_node"] == to_node,
                    to_socket is None or to_socket in {info["to_socket"], info["to_socket_identifier"]},
                ]
            )
            if matches_id or (not link_id and matches_endpoints):
                _remove_link(node_tree, link)
                removed.append(info)
        if not removed:
            return skill_error("No matching node links", "No link matched the provided id or endpoints.")
        return skill_success(
            f"Disconnected {len(removed)} node link(s)",
            node_tree_ref=resolved,
            removed_links=removed,
            count=len(removed),
            prompt="Use list_node_links to verify the graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to disconnect node links")


def set_node_input(node_tree_ref: Mapping[str, Any], node_name: str, socket: str, value: Any) -> dict:
    """Set a node input socket value."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_node_tree(bpy, node_tree_ref)
        if error:
            return error
        node = _collection_get(node_tree.nodes, node_name)
        if node is None:
            return skill_error(f"Node not found: {node_name}", f"No node named '{node_name}'.")
        target = _get_socket(node.inputs, socket)
        if target is None:
            return skill_error(
                f"Input socket not found: {socket}", f"Available inputs: {', '.join(_socket_names(node.inputs))}"
            )
        normalized = _set_socket_value(target, value)
        return skill_success(
            f"Set {socket} on {node_name}",
            node_tree_ref=resolved,
            node_name=node_name,
            socket=socket,
            value=normalized,
            prompt="Use get_node_value or render/capture tools to validate the result.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set {socket} on {node_name}")


def get_node_value(node_tree_ref: Mapping[str, Any], node_name: str, socket: str | None = None) -> dict:
    """Get one input socket value or all socket values for a node."""
    try:
        import bpy

        node_tree, resolved, error = _resolve_node_tree(bpy, node_tree_ref)
        if error:
            return error
        node = _collection_get(node_tree.nodes, node_name)
        if node is None:
            return skill_error(f"Node not found: {node_name}", f"No node named '{node_name}'.")
        if socket:
            target = _get_socket(node.inputs, socket) or _get_socket(node.outputs, socket)
            if target is None:
                return skill_error(f"Socket not found: {socket}", "The node has no matching input or output socket.")
            return skill_success(
                f"Read {socket} on {node_name}",
                node_tree_ref=resolved,
                node_name=node_name,
                socket=_socket_info(target),
                value=_socket_value(target),
                prompt="Use set_node_input for mutable input sockets.",
            )
        return skill_success(
            f"Read node values for {node_name}",
            node_tree_ref=resolved,
            node_name=node_name,
            inputs=[_socket_info(item) for item in _socket_items(node.inputs)],
            outputs=[_socket_info(item) for item in _socket_items(node.outputs)],
            prompt="Use list_node_sockets to inspect socket identifiers.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to read node values for {node_name}")


def create_material_with_nodes(material_name: str, template: str = "principled") -> dict:
    """Create or initialize a node-based material."""
    try:
        import bpy

        material = _get_material(bpy, material_name, create=True)
        if material is None:
            return skill_error(f"Material not found: {material_name}", "Material could not be created.")
        node_tree = _ensure_material_nodes(material)
        if template == "emission":
            output = _collection_get(node_tree.nodes, "Material Output")
            emission = _collection_get(node_tree.nodes, "Emission") or _create_node_in_tree(
                node_tree, "ShaderNodeEmission"
            )
            emission.name = "Emission"
            if output is not None:
                out_socket = _get_socket(emission.outputs, "Emission")
                surface = _get_socket(output.inputs, "Surface")
                if out_socket is not None and surface is not None:
                    node_tree.links.new(out_socket, surface)
        elif template not in {"principled", "default", ""}:
            return skill_error("Unsupported material template", f"Unsupported template: {template}")
        return skill_success(
            f"Created material node graph for {material_name}",
            material_name=material.name,
            template=template,
            node_count=len(_iter_collection(node_tree.nodes)),
            prompt="Use create_node, connect_nodes, or set_principled_inputs for graph edits.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create material {material_name}")


def assign_texture_node(material_name: str, image_path: str, target_socket: str = "Base Color") -> dict:
    """Create an image texture node and connect it to a Principled input."""
    path = Path(image_path).expanduser()
    if not path.is_file():
        return skill_error(f"Image not found: {path}", f"No image exists at '{path}'.")
    try:
        import bpy

        material = _get_material(bpy, material_name)
        if material is None:
            return skill_error(f"Material not found: {material_name}", f"No material named '{material_name}'.")
        node_tree = _ensure_material_nodes(material)
        image = bpy.data.images.load(str(path), check_existing=True)
        node = _create_node_in_tree(node_tree, "ShaderNodeTexImage")
        node.name = f"{path.stem} Texture"
        node.image = image
        principled = _find_principled_node(node_tree.nodes)
        if principled is None:
            return skill_error(
                f"No Principled BSDF node in {material_name}", "Create or restore a Principled node first."
            )
        color = _get_socket(node.outputs, "Color")
        target = _get_socket(principled.inputs, target_socket)
        if color is None or target is None:
            return skill_error(
                "Texture connection sockets not found",
                f"Could not connect Color to {target_socket}.",
            )
        link = node_tree.links.new(color, target)
        return skill_success(
            f"Assigned texture to {material_name}",
            material_name=material_name,
            image_path=str(path),
            image_name=getattr(image, "name", None),
            node=_node_info(node),
            link=_link_info(link),
            target_socket=target_socket,
            prompt="Use list_node_links or render/capture tools to validate the material.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to assign texture to {material_name}")


def set_principled_inputs(material_name: str, inputs: Mapping[str, Any], node_name: str = "Principled BSDF") -> dict:
    """Set multiple Principled BSDF inputs."""
    opts, error = _ensure_mapping(inputs, "inputs")
    if error:
        return error
    try:
        import bpy

        material = _get_material(bpy, material_name)
        if material is None:
            return skill_error(f"Material not found: {material_name}", f"No material named '{material_name}'.")
        if not getattr(material, "use_nodes", False) or getattr(material, "node_tree", None) is None:
            return skill_error(f"Material {material_name} does not use nodes", "Enable material nodes first.")
        node = _find_principled_node(material.node_tree.nodes, node_name)
        if node is None:
            return skill_error(
                f"No Principled BSDF node in {material_name}", "This tool edits Principled BSDF nodes only."
            )
        changed = {}
        missing = []
        for input_name, value in opts.items():
            socket = _get_socket(node.inputs, input_name)
            if socket is None:
                missing.append(input_name)
                continue
            changed[input_name] = _set_socket_value(socket, value)
        if missing:
            return skill_error(
                "Input not found on Principled BSDF",
                f"Missing inputs: {', '.join(missing)}. Available inputs: {', '.join(_socket_names(node.inputs))}",
            )
        return skill_success(
            f"Set {len(changed)} Principled input(s) on {material_name}",
            material_name=material_name,
            node_name=getattr(node, "name", node_name),
            values=changed,
            prompt="Use get_node_value or render/capture tools to validate the material.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set Principled inputs on {material_name}")


def create_geometry_node_group(name: str, template: str = "empty") -> dict:
    """Create or return a Geometry Nodes node group."""
    try:
        import bpy

        group = _collection_get(bpy.data.node_groups, name)
        created = False
        if group is None:
            group = bpy.data.node_groups.new(name, "GeometryNodeTree")
            created = True
        if template == "pass_through":
            _create_passthrough_geometry_group(group)
        elif template not in {"empty", "default", ""}:
            return skill_error("Unsupported geometry node template", f"Unsupported template: {template}")
        return skill_success(
            f"{'Created' if created else 'Loaded'} Geometry Nodes group {name}",
            group_name=getattr(group, "name", name),
            template=template,
            created=created,
            node_count=len(_iter_collection(group.nodes)),
            prompt="Use assign_geometry_node_group to attach this group to an object.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create Geometry Nodes group {name}")


def assign_geometry_node_group(object_name: str, group_name: str, modifier_name: str = "Geometry Nodes") -> dict:
    """Assign a Geometry Nodes group to an object's modifier."""
    try:
        import bpy

        obj = _collection_get(bpy.data.objects, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        if getattr(obj, "type", None) != "MESH":
            return skill_error(f"{object_name} is not a mesh", "Geometry Nodes modifiers require a mesh object.")
        group = _collection_get(bpy.data.node_groups, group_name)
        if group is None:
            return skill_error(f"Node group not found: {group_name}", f"No node group named '{group_name}'.")
        modifier = _get_geometry_modifier(obj, modifier_name) or _new_modifier(obj, modifier_name)
        modifier.node_group = group
        return skill_success(
            f"Assigned Geometry Nodes group {group_name} to {object_name}",
            object_name=object_name,
            modifier_name=modifier.name,
            group_name=getattr(group, "name", group_name),
            prompt="Use set_geometry_node_modifier_input or evaluate_geometry_nodes_info next.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to assign Geometry Nodes group {group_name}")


def set_geometry_node_modifier_input(object_name: str, modifier_name: str, input_name: str, value: Any) -> dict:
    """Set an exposed Geometry Nodes modifier input."""
    try:
        import bpy

        obj = _collection_get(bpy.data.objects, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier = _get_geometry_modifier(obj, modifier_name)
        if modifier is None:
            return skill_error(
                f"Modifier not found: {modifier_name}", f"No Geometry Nodes modifier named '{modifier_name}'."
            )
        group = getattr(modifier, "node_group", None)
        if group is None:
            return skill_error(f"Modifier {modifier_name} has no node group", "Assign a node group first.")
        identifier = _modifier_input_identifier(group, input_name)
        _modifier_set(modifier, identifier, value)
        try:
            obj.update_tag()
        except Exception:
            pass
        return skill_success(
            f"Set Geometry Nodes modifier input {input_name}",
            object_name=object_name,
            modifier_name=modifier.name,
            input_name=input_name,
            identifier=identifier,
            value=_modifier_get(modifier, identifier),
            prompt="Use evaluate_geometry_nodes_info to inspect exposed inputs.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set Geometry Nodes modifier input {input_name}")


def evaluate_geometry_nodes_info(object_name: str, modifier_name: str) -> dict:
    """Return structured information for a Geometry Nodes modifier and group."""
    try:
        import bpy

        obj = _collection_get(bpy.data.objects, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier = _get_geometry_modifier(obj, modifier_name)
        if modifier is None:
            return skill_error(
                f"Modifier not found: {modifier_name}", f"No Geometry Nodes modifier named '{modifier_name}'."
            )
        group = getattr(modifier, "node_group", None)
        if group is None:
            return skill_error(f"Modifier {modifier_name} has no node group", "Assign a node group first.")
        inputs = []
        for socket in _interface_sockets(group):
            identifier = _socket_identifier(socket)
            inputs.append(
                {
                    "name": _socket_name(socket),
                    "identifier": identifier,
                    "value": _modifier_get(modifier, identifier),
                    "in_out": getattr(socket, "in_out", None),
                    "type": getattr(socket, "socket_type", None) or getattr(socket, "type", None),
                }
            )
        return skill_success(
            f"Evaluated Geometry Nodes info for {object_name}",
            object_name=object_name,
            modifier_name=modifier.name,
            group_name=getattr(group, "name", None),
            node_count=len(_iter_collection(group.nodes)),
            link_count=len(_iter_collection(group.links)),
            inputs=inputs,
            prompt="Use list_nodes or set_geometry_node_modifier_input for further edits.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to evaluate Geometry Nodes info for {object_name}")


def get_compositor_node_tree() -> dict:
    """Return the compositor node tree for the current scene."""
    try:
        import bpy

        scene = bpy.context.scene
        if not getattr(scene, "use_nodes", False):
            return skill_error(
                "Compositor nodes not enabled",
                "Enable compositor nodes (scene.use_nodes = True) before accessing the node tree.",
            )
        node_tree = getattr(scene, "node_tree", None)
        if node_tree is None:
            return skill_error(
                "No compositor node tree",
                "The scene has no compositor node tree.",
            )
        nodes = []
        for node in _iter_collection(node_tree.nodes):
            nodes.append(_node_info(node))
        links = [_link_info(link) for link in _iter_collection(node_tree.links)]
        return skill_success(
            f"Compositor node tree: {len(nodes)} nodes, {len(links)} links",
            nodes=nodes,
            links=links,
            node_count=len(nodes),
            link_count=len(links),
            prompt="Use list_nodes with {kind: compositor} for more detailed inspection.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to get compositor node tree")


def list_all_node_graphs() -> dict:
    """List all node graphs (material, geometry, compositor) in the scene."""
    try:
        import bpy

        graphs = []

        # Material node trees
        for material in _iter_collection(bpy.data.materials):
            if getattr(material, "use_nodes", False) and getattr(material, "node_tree", None) is not None:
                nt = material.node_tree
                graphs.append(
                    {
                        "kind": "shader",
                        "name": material.name,
                        "type": "material",
                        "node_count": len(_iter_collection(nt.nodes)),
                        "link_count": len(_iter_collection(nt.links)),
                    }
                )

        # Geometry node groups
        for group in _iter_collection(bpy.data.node_groups):
            if _node_group_type(group) in {"GeometryNodeTree", "GEOMETRY"}:
                graphs.append(
                    {
                        "kind": "geometry",
                        "name": group.name,
                        "type": "geometry_nodes",
                        "node_count": len(_iter_collection(group.nodes)),
                        "link_count": len(_iter_collection(group.links)),
                    }
                )

        # Compositor node tree
        scene = bpy.context.scene
        if getattr(scene, "use_nodes", False) and getattr(scene, "node_tree", None) is not None:
            nt = scene.node_tree
            graphs.append(
                {
                    "kind": "compositor",
                    "name": "Compositor",
                    "type": "compositor",
                    "node_count": len(_iter_collection(nt.nodes)),
                    "link_count": len(_iter_collection(nt.links)),
                }
            )

        return skill_success(
            f"Found {len(graphs)} node graph(s)",
            node_graphs=graphs,
            count=len(graphs),
            prompt="Use list_nodes or get_compositor_node_tree to inspect a specific graph.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list all node graphs")
