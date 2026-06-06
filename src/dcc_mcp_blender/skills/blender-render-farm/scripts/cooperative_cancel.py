"""Cooperatively cancel the currently running farm operation.

Unlike ``cancel_render_job`` which targets a specific job on the farm
manager, this tool tells the *local* DCC process to abort a long-running
farm operation (e.g. validate_scene_for_farm or submit_render_job) that
is still in progress.
"""

# Import future modules
from __future__ import annotations

# Import local modules
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def cooperative_cancel() -> dict:
    """Signal cooperative cancellation for the currently running farm operation.

    This sets a cancellation flag that the running farm operation checks
    via ``check_dcc_cancelled()`` at key checkpoints:

    - ``validate_scene_for_farm``: at start and inside image/library loops.
    - ``write_render_job``: before scene inspection.
    - ``submit_render_job``: before farm submission.
    - ``get_render_job_status``: before API calls.
    - ``list_render_jobs``: before API calls.
    - ``cancel_render_job``: before API calls.
    - ``render_farm_status``: before each API call.

    When the flag is set, the checkpoint raises ``CancelledError`` and the
    operation aborts promptly instead of continuing.

    Outside an MCP request context (e.g. standalone scripting), the
    cancellation flag has no effect.

    Returns:
        ToolResult dict confirming the cancellation was signaled.
    """

    try:
        from dcc_mcp_core import set_cancelled  # noqa: PLC0415

        set_cancelled()
        return skill_success(
            "Cooperative cancellation signaled",
            prompt="The currently running farm operation will abort at its next checkpoint.",
            cancelled=True,
        )
    except ImportError:
        return skill_error(
            "Cancellation not available",
            "dcc_mcp_core.set_cancelled could not be imported; "
            "ensure the adapter is running inside a valid MCP session",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to signal cooperative cancellation")


@skill_entry
def main(**kwargs):
    return cooperative_cancel(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
