"""Execute a Python code snippet inside Blender."""

from __future__ import annotations

import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Dict, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_blender._script_guard import guard_arbitrary_execution


def execute_python(code: str, context: Optional[Dict[str, Any]] = None) -> dict:
    """Execute a Python code snippet inside Blender's interpreter.

    The code has full access to ``bpy`` and the entire Blender Python API.

    Refuses immediately when ``DCC_MCP_BLENDER_DISABLE_ARBITRARY_SCRIPT`` or
    ``DCC_MCP_BLENDER_DISABLE_EXECUTE_PYTHON`` is set.

    Args:
        code: Python source code to execute.
        context: Optional dictionary of variables to inject into the execution namespace.

    Returns:
        ActionResultModel dict with stdout, stderr, and any result value.
    """
    refusal = guard_arbitrary_execution("execute_python")
    if refusal is not None:
        return refusal

    try:
        import bpy  # noqa: F401 - ensure bpy is available

        namespace: Dict[str, Any] = {"bpy": bpy}
        if context:
            namespace.update(context)

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        result = None
        error = None

        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(compile(code, "<mcp-script>", "exec"), namespace)  # noqa: S102
            result = namespace.get("result")
        except Exception:
            error = traceback.format_exc()

        stdout_output = stdout_buf.getvalue()
        stderr_output = stderr_buf.getvalue()

        if error:
            return skill_error(
                "Script execution failed",
                error,
                stdout=stdout_output,
                stderr=stderr_output + error,
            )

        return skill_success(
            "Script executed successfully",
            stdout=stdout_output,
            stderr=stderr_output,
            result=str(result) if result is not None else None,
            prompt="Script completed. Check stdout for output.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to execute Python code")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`execute_python`."""
    return execute_python(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
