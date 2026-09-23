"""Shared opt-out guard for the arbitrary-execution escape hatches.

``blender-scripting`` exposes two escape hatches that run arbitrary Python
inside Blender's interpreter: ``execute_python`` and ``execute_script_file``.
Studios running fleet or unattended workloads need a hard, centrally managed
opt-out, so both entries consult
:func:`dcc_mcp_blender._env.resolve_execute_python_disabled` before they do
anything else.

Keeping the refusal in one module means the two entries cannot drift apart:
both reject with the same error code, name the exact variable that caused the
refusal, and never execute user code while the opt-out is active.
"""

# Import future modules
from __future__ import annotations

# Import built-in modules
from typing import Optional

# Import third-party modules
from dcc_mcp_core.skill import skill_error

# Import local modules
from ._env import resolve_execute_python_opt_outs

#: Stable machine-readable error code returned by every guarded entry.
ERROR_ARBITRARY_EXECUTION_DISABLED = "arbitrary_execution_disabled"


def guard_arbitrary_execution(tool_name: str) -> Optional[dict]:
    """Return a refusal result when arbitrary execution is switched off.

    Args:
        tool_name: Public tool name used in the user-facing message.

    Returns:
        A ``skill_error`` result dict when the opt-out is active, otherwise
        ``None`` so callers can continue executing.
    """
    opt_outs = resolve_execute_python_opt_outs()
    if not opt_outs:
        return None

    return skill_error(
        f"{tool_name} is disabled by configuration",
        ERROR_ARBITRARY_EXECUTION_DISABLED,
        prompt=(
            f"Arbitrary script execution is switched off by {', '.join(opt_outs)}. "
            "Use the typed skill tools instead, or unset the variable to re-enable "
            "this escape hatch."
        ),
        possible_solutions=[
            "Use the typed, schema-validated skill tools for this operation.",
            *[f"Unset {name} to re-enable arbitrary script execution." for name in opt_outs],
        ],
        disabled_by=list(opt_outs),
    )
