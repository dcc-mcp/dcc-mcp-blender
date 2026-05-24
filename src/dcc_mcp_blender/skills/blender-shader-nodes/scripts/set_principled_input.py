"""Set common Principled BSDF input values on a Blender material."""

from __future__ import annotations

from typing import Any, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _find_principled_node(nodes: Any, node_name: str):
    node = nodes.get(node_name) if hasattr(nodes, "get") else None
    if node is not None:
        return node

    for candidate in nodes:
        if getattr(candidate, "type", "") == "BSDF_PRINCIPLED":
            return candidate
    return None


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
        return value + [1.0]
    return value


def set_principled_input(
    material_name: str,
    input_name: str,
    value: Any,
    node_name: str = "Principled BSDF",
) -> dict:
    """Set a Principled BSDF input value."""
    try:
        import bpy

        mat = bpy.data.materials.get(material_name)
        if mat is None:
            return skill_error(f"Material not found: {material_name}", f"No material named '{material_name}'.")
        if not mat.use_nodes or mat.node_tree is None:
            return skill_error(f"Material {material_name} does not use nodes", "Enable material nodes first.")

        node = _find_principled_node(mat.node_tree.nodes, node_name)
        if node is None:
            return skill_error(
                f"No Principled BSDF node in {material_name}",
                "This tool edits the material's Principled BSDF shader.",
            )

        socket: Optional[Any] = node.inputs.get(input_name) if hasattr(node.inputs, "get") else None
        if socket is None:
            return skill_error(
                f"Input not found on Principled BSDF: {input_name}",
                f"Available inputs: {', '.join(str(name) for name in node.inputs.keys())}",
            )

        socket.default_value = _normalise_value(socket.default_value, value)
        return skill_success(
            f"Set {input_name} on {material_name}",
            material_name=material_name,
            node_name=getattr(node, "name", node_name),
            input_name=input_name,
            value=socket.default_value,
            prompt="Use render_scene or capture_viewport to inspect the material result.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set {input_name} on {material_name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_principled_input`."""
    return set_principled_input(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
