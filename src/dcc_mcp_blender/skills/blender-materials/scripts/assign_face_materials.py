"""Bounded typed face-material operation."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._face_material_ops import assign_face_materials


@skill_entry
def main(**kwargs) -> dict:
    """Delegate to the revision-pinned original-mesh operation."""
    return assign_face_materials(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
