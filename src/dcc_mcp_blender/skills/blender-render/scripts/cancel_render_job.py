"""Cancel an owned Blender render job."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._render_job_ops import cancel_render_job


@skill_entry
def main(**kwargs) -> dict:
    return cancel_render_job(**kwargs)
