"""Create a dimensioned, closed solid pointed arch."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._architectural_mesh import create_pointed_arch


@skill_entry
def main(**kwargs):
    return create_pointed_arch(**kwargs)
