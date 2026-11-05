"""Regression guards for the issue #188 render-job findings.

The five findings in dcc-mcp-blender#188 were rechecked against the current
adapter. ``start_render_job`` is no longer EXR-only (fixed in #195), and owned
render jobs must be polled through ``get_render_job`` because the core
``jobs_get_status`` registry / ``dcc-mcp-cli --wait`` cannot track the detached
worker. These tests pin that published contract so a future edit cannot
silently reintroduce either DX regression. No ``bpy`` is needed here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from dcc_mcp_blender import _render_job_ops

_SKILL_DIR = Path(__file__).resolve().parents[1] / "src" / "dcc_mcp_blender" / "skills" / "blender-render"


def _tool(name):
    tools = yaml.safe_load((_SKILL_DIR / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    return next(tool for tool in tools if tool["name"] == name)


def test_start_render_job_publishes_display_ready_formats():
    """#188: output is not EXR-only; the YAML enum must not drift from the code."""
    enum = set(_tool("start_render_job")["input_schema"]["properties"]["output_format"]["enum"])
    assert {"PNG", "JPEG", "TIFF", "BMP"} <= enum
    assert enum == set(_render_job_ops._OUTPUT_FORMATS)


def test_start_render_job_declares_get_render_job_poll_path():
    """#188: ``--wait`` cannot track owned jobs, so the poll hint must stay."""
    assert "blender_render__get_render_job" in _tool("start_render_job")["next-tools"]["on-success"]
