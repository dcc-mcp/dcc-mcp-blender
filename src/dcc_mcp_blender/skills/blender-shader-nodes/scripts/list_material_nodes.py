"""List shader nodes on a Blender material."""

from __future__ import annotations

from typing import Any, Iterable, List

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _socket_names(sockets: Any) -> List[str]:
    if hasattr(sockets, "keys"):
        try:
            return [str(name) for name in sockets.keys()]
        except Exception:
            pass

    try:
        items: Iterable[Any] = sockets
    except TypeError:
        return []
    return [str(getattr(socket, "name", socket)) for socket in items]


def list_material_nodes(material_name: str, include_sockets: bool = True) -> dict:
    """List nodes in a material's shader graph."""
    try:
        import bpy

        mat = bpy.data.materials.get(material_name)
        if mat is None:
            return skill_error(f"Material not found: {material_name}", f"No material named '{material_name}'.")
        if not mat.use_nodes or mat.node_tree is None:
            return skill_error(f"Material {material_name} does not use nodes", "Enable material nodes first.")

        nodes = []
        for node in mat.node_tree.nodes:
            info = {
                "name": node.name,
                "type": node.type,
                "label": getattr(node, "label", ""),
            }
            if include_sockets:
                info["inputs"] = _socket_names(node.inputs)
                info["outputs"] = _socket_names(node.outputs)
            nodes.append(info)

        return skill_success(
            f"Found {len(nodes)} shader nodes on {material_name}",
            material_name=material_name,
            nodes=nodes,
            count=len(nodes),
            prompt="Use set_principled_input to tune common Principled BSDF inputs.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to list shader nodes for {material_name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_material_nodes`."""
    return list_material_nodes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
