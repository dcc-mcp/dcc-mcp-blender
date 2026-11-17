"""Start isolated tree diagnostic renders without changing the active scene."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._tree_diagnostic_ops import start_tree_diagnostic


@skill_entry
def main(**kwargs):
    return start_tree_diagnostic(**kwargs)
