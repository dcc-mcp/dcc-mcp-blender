"""Typed bounded native data geometry."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._data_geometry import create_mesh_from_data


@skill_entry
def main(**kwargs):
    return create_mesh_from_data(**kwargs)
