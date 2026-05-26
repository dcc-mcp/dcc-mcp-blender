"""List shader nodes on a Blender material."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._node_graph_ops import list_nodes


def list_material_nodes(material_name: str, include_sockets: bool = True) -> dict:
    """List nodes in a material's shader graph."""
    result = list_nodes({"kind": "shader", "material_name": material_name})
    if result.get("success"):
        result["context"]["material_name"] = material_name
        if not include_sockets:
            for node in result["context"].get("nodes", []):
                node.pop("inputs", None)
                node.pop("outputs", None)
    return result


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_material_nodes`."""
    return list_material_nodes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
