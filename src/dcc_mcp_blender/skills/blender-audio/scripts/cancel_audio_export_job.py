"""Owned audio export job entry point."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._audio_export_ops import cancel_audio_export_job


@skill_entry
def main(**kwargs) -> dict:
    return cancel_audio_export_job(**kwargs)
