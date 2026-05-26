"""Set common Principled BSDF input values on a Blender material."""

from __future__ import annotations

from typing import Any

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._node_graph_ops import set_principled_inputs


def set_principled_input(
    material_name: str,
    input_name: str,
    value: Any,
    node_name: str = "Principled BSDF",
) -> dict:
    """Set a Principled BSDF input value."""
    result = set_principled_inputs(material_name=material_name, inputs={input_name: value}, node_name=node_name)
    if result.get("success"):
        result["context"]["input_name"] = input_name
        result["context"]["value"] = result["context"].get("values", {}).get(input_name)
    return result


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_principled_input`."""
    return set_principled_input(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
