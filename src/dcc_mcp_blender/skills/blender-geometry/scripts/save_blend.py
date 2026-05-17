"""Save the current Blender file."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def save_blend(path: str) -> dict:
    """Save the current file using ``bpy.ops.wm.save_as_mainfile``."""
    try:
        import bpy

        bpy.ops.wm.save_as_mainfile(filepath=path)
        return skill_success(f"Saved blend file: {path}", filepath=path, prompt="Blend file saved.")
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to save blend file: {path}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`save_blend`."""
    return save_blend(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
