"""Environment-variable resolution for ``BlenderMcpServer``.

Centralises every ``DCC_MCP_BLENDER_*`` env var used by the server so the
composition root in :mod:`dcc_mcp_blender.server` stays a thin orchestrator.

All helpers are pure functions: they read :data:`os.environ` and return
plain Python values; they never mutate global state.
"""

# Import future modules
from __future__ import annotations

# Import built-in modules
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Public env-var names ─────────────────────────────────────────────────
ENV_METRICS = "DCC_MCP_BLENDER_METRICS"
ENV_JOB_STORAGE = "DCC_MCP_BLENDER_JOB_STORAGE"
ENV_STRICT_SKILL_SCAN = "DCC_MCP_BLENDER_STRICT_SKILL_SCAN"
ENV_ENABLE_WORKFLOWS = "DCC_MCP_BLENDER_ENABLE_WORKFLOWS"
ENV_ENABLE_GATEWAY_FAILOVER = "DCC_MCP_BLENDER_ENABLE_GATEWAY_FAILOVER"
ENV_DISABLE_EXECUTE_PYTHON = "DCC_MCP_BLENDER_DISABLE_EXECUTE_PYTHON"
ENV_DISABLE_ARBITRARY_SCRIPT = "DCC_MCP_BLENDER_DISABLE_ARBITRARY_SCRIPT"
ENV_BLENDER_PATH = "DCC_MCP_BLENDER_PATH"
ENV_BLENDER_VERSION = "BLENDER_VERSION"
DEFAULT_JOB_DB_FILENAME = "jobs.db"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def resolve_execute_python_disabled() -> bool:
    """Return True when ``execute_python`` must refuse all calls.

    ``DCC_MCP_BLENDER_DISABLE_ARBITRARY_SCRIPT`` implies this flag.  Used by
    ``blender-scripting`` scripts so studios can enforce skills-first workflows.
    """
    if _env_truthy(ENV_DISABLE_ARBITRARY_SCRIPT):
        return True
    return _env_truthy(ENV_DISABLE_EXECUTE_PYTHON)


def resolve_metrics_enabled(metrics_enabled: Optional[bool]) -> bool:
    """Resolve the Prometheus ``/metrics`` endpoint flag.

    Priority: explicit argument > ``DCC_MCP_BLENDER_METRICS=1`` > ``False``.
    """
    if metrics_enabled is not None:
        return bool(metrics_enabled)
    return os.environ.get(ENV_METRICS, "").strip() == "1"


def resolve_job_storage(job_storage_path: Optional[str]) -> Optional[str]:
    """Resolve the SQLite job-storage path.

    Returns ``None`` when callers should leave whatever path
    :class:`DccServerBase._init_job_persistence` selected.  Returns the
    empty string ``""`` when the caller passed ``""`` explicitly to
    request in-memory operation (no persistence).
    """
    if job_storage_path is not None:
        return job_storage_path

    env_path = os.environ.get(ENV_JOB_STORAGE, "").strip()
    if env_path:
        return env_path

    # Default: use platform data dir
    return None


def resolve_strict_skill_scan() -> bool:
    """Return True when ``register_builtin_actions`` should raise on scan errors.

    When ``DCC_MCP_BLENDER_STRICT_SKILL_SCAN=1``, silently-skipped skill
    directories raise ``ValueError`` at startup instead of disappearing
    into a debug-level log line.
    """
    return _env_truthy(ENV_STRICT_SKILL_SCAN)


def resolve_enable_workflows(enable_workflows: Optional[bool] = None) -> bool:
    """Return True when workflow engine surface should be enabled.

    Opt-in workflow engine surface (``workflows.run``, ``workflows.resume``,
    ``workflows.list_runs`` MCP tools).  Off by default so the minimal-mode
    tools/list stays small.

    Priority: explicit ``enable_workflows`` argument >
    ``DCC_MCP_BLENDER_ENABLE_WORKFLOWS`` truthy tokens > ``False``.
    """
    if enable_workflows is not None:
        return bool(enable_workflows)
    return _env_truthy(ENV_ENABLE_WORKFLOWS)


def resolve_enable_gateway_failover(enable_gateway_failover: Optional[bool]) -> bool:
    """Resolve gateway failover flag.

    Priority: explicit argument > ``DCC_MCP_BLENDER_ENABLE_GATEWAY_FAILOVER`` env var > ``True``.
    """
    if enable_gateway_failover is not None:
        return bool(enable_gateway_failover)
    if os.environ.get(ENV_ENABLE_GATEWAY_FAILOVER, "").strip():
        return _env_truthy(ENV_ENABLE_GATEWAY_FAILOVER)
    return True  # Default: enable gateway failover


def resolve_blender_path() -> Optional[str]:
    """Resolve Blender executable path.

    Returns the path from ``DCC_MCP_BLENDER_PATH`` env var, or ``None``
    to use system default.
    """
    path = os.environ.get(ENV_BLENDER_PATH, "").strip()
    return path if path else None
