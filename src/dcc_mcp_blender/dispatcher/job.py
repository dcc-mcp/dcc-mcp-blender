"""Core-backed job aliases for Blender dispatcher compatibility."""

# Import future modules
from __future__ import annotations

from dcc_mcp_core import DEFAULT_UI_JOB_TIMEOUT_MS, HostUiJobEntry, current_job

DEFAULT_JOB_TIMEOUT_MS = DEFAULT_UI_JOB_TIMEOUT_MS
_JobEntry = HostUiJobEntry
_current_job = current_job

__all__ = ["DEFAULT_JOB_TIMEOUT_MS", "_JobEntry", "_current_job"]
