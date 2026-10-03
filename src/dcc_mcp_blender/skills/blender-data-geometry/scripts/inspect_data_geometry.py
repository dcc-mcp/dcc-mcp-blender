"""Inspect native bounded geometry."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._data_geometry import inspect_data_geometry


@skill_entry
def main(**kwargs):
    return inspect_data_geometry(**kwargs)
