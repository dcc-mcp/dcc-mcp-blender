"""Save an audited self-contained native scene copy."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._portable_scene import save_portable_scene_copy


@skill_entry
def main(**kwargs):
    return save_portable_scene_copy(**kwargs)
