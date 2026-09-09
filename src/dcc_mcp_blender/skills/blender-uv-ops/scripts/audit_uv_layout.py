"""Read source UV data without changing Blender context."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._uv_quality import audit_uv_layout


@skill_entry
def main(**kwargs) -> dict:
    return audit_uv_layout(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
