"""Remove a revision-pinned Geometry Nodes interface socket."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._geometry_interface_ops import remove_geometry_node_socket


@skill_entry
def main(**kwargs) -> dict:
    return remove_geometry_node_socket(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
