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
#: Advisory readiness probe timeout (positive integer seconds) — parity with
#: Maya / Houdini ``_readiness`` wiring.
ENV_READINESS_TIMEOUT_SECS = "DCC_MCP_BLENDER_READINESS_TIMEOUT_SECS"
#: Opt out of the four ``project_*`` MCP tools (``"0"`` disables).
ENV_PROJECT_TOOLS = "DCC_MCP_BLENDER_PROJECT_TOOLS"
#: Opt out of MCP resource publishing such as ``scene://current`` (``"0"`` disables).
ENV_RESOURCES = "DCC_MCP_BLENDER_RESOURCES"
#: Enable the opt-in lexical+vector semantic skill recall augmentation.
ENV_SEMANTIC_INDEX = "DCC_MCP_BLENDER_SEMANTIC_INDEX"
#: ``hashed`` (default, zero-dep) or ``onnx`` (requires the ``[semantic]`` extra).
ENV_SEMANTIC_EMBEDDER = "DCC_MCP_BLENDER_SEMANTIC_EMBEDDER"
DEFAULT_JOB_DB_FILENAME = "jobs.db"

_TRUTHY = ("1", "true", "yes", "on")


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _resolve_opt_out(env_name: str, flag: Optional[bool]) -> bool:
    """Resolve an opt-out flag: explicit arg > env (``"0"`` disables) > ``True``."""
    if flag is not None:
        return bool(flag)
    raw = os.environ.get(env_name)
    if raw is None:
        return True
    return raw.strip() != "0"


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


def resolve_readiness_timeout_secs(readiness_timeout_secs: Optional[int] = None) -> Optional[int]:
    """Resolve :data:`ENV_READINESS_TIMEOUT_SECS` into a positive integer or ``None``.

    Priority: explicit argument > ``DCC_MCP_BLENDER_READINESS_TIMEOUT_SECS`` > ``None``.
    Invalid / non-positive values resolve to ``None`` (no advisory timeout).
    """
    if readiness_timeout_secs is not None:
        try:
            val = int(readiness_timeout_secs)
        except (TypeError, ValueError):
            return None
        return val if val > 0 else None

    raw = os.environ.get(ENV_READINESS_TIMEOUT_SECS)
    if not raw or not raw.strip():
        return None
    try:
        val = int(raw.strip())
    except ValueError:
        logger.warning(
            "Ignoring invalid %s=%r (expected positive integer seconds)",
            ENV_READINESS_TIMEOUT_SECS,
            raw,
        )
        return None
    return val if val > 0 else None


def resolve_project_tools_enabled(flag: Optional[bool] = None) -> bool:
    """Resolve whether the ``project_*`` tools should be wired in.

    Priority: explicit ``flag`` > ``DCC_MCP_BLENDER_PROJECT_TOOLS`` (``"0"`` disables) > ``True``.
    """
    return _resolve_opt_out(ENV_PROJECT_TOOLS, flag)


def resolve_resources_enabled(flag: Optional[bool] = None) -> bool:
    """Resolve whether MCP resource publishing should run.

    Priority: explicit ``flag`` > ``DCC_MCP_BLENDER_RESOURCES`` (``"0"`` disables) > ``True``.
    """
    return _resolve_opt_out(ENV_RESOURCES, flag)


def resolve_semantic_index_enabled(env: Optional[dict] = None) -> bool:
    """Return ``True`` when ``DCC_MCP_BLENDER_SEMANTIC_INDEX`` is truthy (default off)."""
    environ = env if env is not None else os.environ
    return str(environ.get(ENV_SEMANTIC_INDEX, "")).strip().lower() in _TRUTHY


def resolve_semantic_embedder_kind(env: Optional[dict] = None) -> str:
    """Return the requested embedder kind: ``"hashed"`` (default) or ``"onnx"``."""
    environ = env if env is not None else os.environ
    kind = str(environ.get(ENV_SEMANTIC_EMBEDDER, "hashed")).strip().lower()
    return "onnx" if kind == "onnx" else "hashed"
