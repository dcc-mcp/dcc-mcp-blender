"""Execute a Python script file inside Blender."""

from __future__ import annotations

import io
import traceback
from contextlib import redirect_stderr, redirect_stdout

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_blender._script_guard import guard_arbitrary_execution


def execute_script_file(filepath: str) -> dict:
    """Execute a Python script file inside Blender's interpreter.

    Refuses immediately when ``DCC_MCP_BLENDER_DISABLE_ARBITRARY_SCRIPT`` or
    ``DCC_MCP_BLENDER_DISABLE_EXECUTE_PYTHON`` is set.

    Args:
        filepath: Absolute path to the Python script file.

    Returns:
        ActionResultModel dict with stdout, stderr output.
    """
    refusal = guard_arbitrary_execution("execute_script_file")
    if refusal is not None:
        return refusal

    try:
        import bpy  # noqa: F401

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                code = f.read()
        except FileNotFoundError:
            return skill_error(f"Script file not found: {filepath}", f"No file at '{filepath}'.")
        except OSError as e:
            return skill_error(f"Cannot read script: {filepath}", str(e))

        namespace = {"bpy": bpy, "__file__": filepath}
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        error = None

        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(compile(code, filepath, "exec"), namespace)  # noqa: S102
        except Exception:
            error = traceback.format_exc()

        stdout_output = stdout_buf.getvalue()
        stderr_output = stderr_buf.getvalue()

        if error:
            return skill_error(
                f"Script execution failed: {filepath}",
                error,
                stdout=stdout_output,
                stderr=stderr_output + error,
            )

        return skill_success(
            f"Script executed: {filepath}",
            filepath=filepath,
            stdout=stdout_output,
            stderr=stderr_output,
            prompt="Script completed successfully.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to execute script: {filepath}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`execute_script_file`."""
    return execute_script_file(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
