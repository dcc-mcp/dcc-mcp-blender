"""Import an FBX file into Blender."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._interchange_ops import import_fbx


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`import_fbx`."""
    return import_fbx(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
