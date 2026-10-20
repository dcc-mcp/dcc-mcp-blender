"""Submit an existing saved scene without loading it into the control host."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._render_job_ops import start_saved_scene_job


@skill_entry
def main(**kwargs) -> dict:
    return start_saved_scene_job(**kwargs)
