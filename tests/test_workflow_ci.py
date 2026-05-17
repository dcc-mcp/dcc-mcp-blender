"""Regression checks for the Blender E2E workflow."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent
E2E_WORKFLOW = ROOT / ".github" / "workflows" / "e2e.yml"


def test_mcporter_calls_use_registered_tool_names():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    stale_prefixed_calls = re.findall(r"blender-ci\.blender_[a-z_]+__[a-z_]+", text)
    assert stale_prefixed_calls == []


def test_mcporter_call_wrapper_fails_unknown_tools():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    assert "call_tool() {" in text
    assert '"code": "ACTION_NOT_FOUND"' in text
    assert "Unknown tool" in text


def test_workflow_server_uses_blender_inprocess_dispatcher():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    assert "from dcc_mcp_blender.host import BlenderCallableDispatcher, BlenderHost" in text
    assert "dispatcher = BlenderCallableDispatcher()" in text
    assert "dcc_mcp_blender.start_server(port=8765, dispatcher=dispatcher)" in text
    assert "host.start()" in text
    assert "host.stop()" in text


def test_execute_python_smoke_call_avoids_shell_key_value_assignment():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    execute_python_calls = re.findall(r"call_tool execute_python \\\s*\n\s*\"code:([^\"]+)\"", text)
    assert execute_python_calls
    assert all(" = " not in code for code in execute_python_calls)
