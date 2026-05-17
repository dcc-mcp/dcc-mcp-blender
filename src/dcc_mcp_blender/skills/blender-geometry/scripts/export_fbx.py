"""Export the current Blender scene to FBX."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def export_fbx(path: str) -> dict:
    """Export the current scene using ``bpy.ops.export_scene.fbx``."""
    try:
        import bpy

        bpy.ops.export_scene.fbx(filepath=path)
        return skill_success(f"Exported FBX: {path}", filepath=path, prompt="FBX exported.")
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to export FBX: {path}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`export_fbx`."""
    return export_fbx(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
