"""Cancel a tree diagnostic worker owned by this Blender process."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._tree_diagnostic_ops import cancel_tree_diagnostic


@skill_entry
def main(**kwargs):
    return cancel_tree_diagnostic(**kwargs)
