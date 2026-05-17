"""Export the current Blender scene to OBJ."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def export_obj(path: str) -> dict:
    """Export OBJ using Blender 3.x/4.x compatible operators."""
    try:
        import bpy

        wm_export = getattr(bpy.ops.wm, "obj_export", None)
        if callable(wm_export):
            wm_export(filepath=path)
        else:
            bpy.ops.export_scene.obj(filepath=path)
        return skill_success(f"Exported OBJ: {path}", filepath=path, prompt="OBJ exported.")
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to export OBJ: {path}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`export_obj`."""
    return export_obj(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
