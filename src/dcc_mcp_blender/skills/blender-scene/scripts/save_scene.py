"""Save the current Blender scene with operator and native-file readback."""

from __future__ import annotations

import os
import stat
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def _absolute_path(bpy, path: str) -> str:
    """Resolve Blender's // syntax before Save As changes the relative base."""
    return os.path.abspath(bpy.path.abspath(path))


def _same_destination(left: str, right: str) -> bool:
    """Accept normal relative/absolute spelling and legitimate filesystem aliases."""
    if os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right)):
        return True
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def _failure(code: str, detail: str, attempted: bool, **context) -> dict:
    return skill_error(
        "Failed to save scene",
        detail,
        error_code=code,
        save_attempted=attempted,
        mutation_applied=None if attempted else False,
        prompt="Inspect the actual scene path and target file before retrying. No automatic retry or rollback was performed.",
        **context,
    )


def save_scene(filepath: Optional[str] = None) -> dict:
    """Save only reports success after FINISHED, matching path and nonempty file.

    File existence is not an integrity/reopen guarantee. Failed saves may have
    already changed files or Blender state; do not retry or delete them here.
    """
    attempted = False
    if filepath is not None and (not isinstance(filepath, str) or not filepath.strip() or "\x00" in filepath):
        return _failure("invalid_filepath", "filepath must be a non-empty path string or omitted.", False)
    try:
        import bpy

        requested_path = filepath if filepath is not None else bpy.data.filepath
        if not isinstance(requested_path, str) or not requested_path:
            return _failure("save_path_required", "The scene has not been saved yet. Please provide a filepath.", False)
        # Resolve the relative base before the operator, but resolve filesystem
        # aliases during readback: a legitimate save may replace a file symlink.
        destination = _absolute_path(bpy, requested_path)
        expected_paths = [destination]
        if filepath is not None and not destination.lower().endswith(".blend"):
            # Blender may append its native extension; allow that exact variant,
            # not an unrelated output path.
            expected_paths.append(destination + ".blend")

        # Native save operators reject Blender-relative // and can resolve
        # plain relative paths differently from bpy.path. Pass the absolute
        # destination already resolved against the pre-save scene.
        attempted = True
        result = (
            bpy.ops.wm.save_as_mainfile(filepath=destination) if filepath is not None else bpy.ops.wm.save_mainfile()
        )
        status = (
            sorted(result)
            if isinstance(result, set) and all(isinstance(item, str) for item in result)
            else type(result).__name__
        )
        if not isinstance(result, set) or result != {"FINISHED"}:
            return _failure(
                "save_not_finished",
                "Blender did not report an unambiguous FINISHED status; an existing target file is not proof of a successful save.",
                True,
                operator_result=status,
            )
        actual_path = bpy.data.filepath
        if not isinstance(actual_path, str) or not actual_path:
            return _failure(
                "save_path_unverified", "Blender did not report a saved scene filepath.", True, operator_result=status
            )
        actual_path = _absolute_path(bpy, actual_path)
        if not any(_same_destination(actual_path, path) for path in expected_paths):
            return _failure(
                "save_path_mismatch",
                "Blender's saved scene filepath does not match the requested destination.",
                True,
                operator_result=status,
                requested_filepath=requested_path,
                actual_filepath=actual_path,
            )
        saved_stat = os.stat(actual_path)
        if not stat.S_ISREG(saved_stat.st_mode) or saved_stat.st_size <= 0:
            return _failure(
                "save_file_unverified",
                "The reported destination is not a nonempty regular file.",
                True,
                operator_result=status,
                actual_filepath=actual_path,
            )
        return skill_success(
            f"Scene saved to {actual_path}",
            filepath=actual_path,
            requested_filepath=requested_path,
            file_size_bytes=saved_stat.st_size,
            operator_result=status,
            verified=True,
            postcondition={"method": "finished_operator_matching_scene_path_nonempty_file"},
            prompt="Save operator, scene path and nonempty file verified. Reopen separately when content integrity must be established.",
        )
    except ImportError:
        return _failure("blender_unavailable", "bpy could not be imported.", attempted)
    except Exception as exc:
        return _failure(
            "save_failed" if attempted else "save_preflight_failed",
            str(exc),
            attempted,
            error_type=type(exc).__name__,
        )


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`save_scene`."""
    return save_scene(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
