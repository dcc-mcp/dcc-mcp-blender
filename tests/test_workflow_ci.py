"""Regression checks for the Blender E2E workflow."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent
E2E_WORKFLOW = ROOT / ".github" / "workflows" / "e2e.yml"
SCRIPTS_DIR = ROOT / ".github" / "scripts"
RUN_BLENDER_E2E = SCRIPTS_DIR / "run_blender_e2e.py"
RUN_DOCKER_E2E = SCRIPTS_DIR / "run_docker_blender_e2e.sh"
START_MCP_SERVER = SCRIPTS_DIR / "start_mcp_server.py"


def test_mcporter_calls_use_registered_tool_names():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    stale_prefixed_calls = re.findall(r"blender-ci\.blender_[a-z_]+__[a-z_]+", text)
    assert stale_prefixed_calls == []


def test_mcporter_call_wrapper_fails_unknown_tools():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    assert "call_tool() {" in text
    assert "set +e" in text
    assert "set -e" in text
    assert '"code": "ACTION_NOT_FOUND"' in text
    assert "Unknown tool" in text


def test_workflow_server_uses_blender_inprocess_dispatcher():
    workflow = E2E_WORKFLOW.read_text(encoding="utf-8")
    text = START_MCP_SERVER.read_text(encoding="utf-8")

    assert ".github/scripts/start_mcp_server.py" in workflow
    assert "from dcc_mcp_blender.host import BlenderCallableDispatcher, BlenderHost" in text
    assert "dispatcher = BlenderCallableDispatcher()" in text
    assert "dcc_mcp_blender.start_server(port=8765, dispatcher=dispatcher)" in text
    assert "host.run_headless(stop_event=stop_event)" in text
    assert "host.stop()" in text


def test_execute_python_smoke_call_avoids_shell_key_value_assignment():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    execute_python_calls = re.findall(r"call_tool execute_python \\\s*\n\s*\"code:([^\"]+)\"", text)
    assert execute_python_calls
    assert all(" = " not in code for code in execute_python_calls)


def test_geometry_export_verification_reads_paths_from_environment():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    assert "export GEOM_BLEND GEOM_FBX GEOM_OBJ" in text
    assert "path = os.environ[key]" in text
    assert "('$GEOM_BLEND', '$GEOM_FBX', '$GEOM_OBJ')" not in text


def test_e2e_workflow_smokes_nodes_and_physics_tools():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    for tool_name in (
        "list_material_nodes",
        "set_principled_input",
        "add_geometry_nodes_modifier",
        "list_geometry_nodes_modifiers",
        "add_rigid_body",
        "set_rigid_body_properties",
        "remove_rigid_body",
    ):
        assert f"call_tool {tool_name}" in text


def test_e2e_workflow_does_not_run_mock_unit_tests():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    assert "Run unit tests (system Python)" not in text
    assert 'pytest tests/ -v --tb=short -m "not e2e and not packaging"' not in text


def test_linux_e2e_runs_in_real_blender_docker_images():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")
    docker_script = RUN_DOCKER_E2E.read_text(encoding="utf-8")

    assert "e2e-linux-docker:" in text
    assert "Run E2E tests in Blender Docker image" in text
    assert ".github/scripts/run_docker_blender_e2e.sh" in text
    assert '"$BLENDER_BIN" --background --python "$workspace/.github/scripts/run_blender_e2e.py"' in docker_script

    images = re.findall(r'blender-image: "(linuxserver/blender:[^"]+)"', text)
    assert images == [
        "linuxserver/blender:4.4.3",
        "linuxserver/blender:4.3.2",
        "linuxserver/blender:4.2.0",
        "linuxserver/blender:3.6.5",
    ]


def test_e2e_workflow_uses_checked_in_ci_scripts():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")
    runner = RUN_BLENDER_E2E.read_text(encoding="utf-8")

    assert "Write Docker E2E runner" not in text
    assert "cat > /tmp/run_e2e.py" not in text
    assert "cat > /tmp/start_mcp_server.py" not in text
    assert "cat > /tmp/start_mcp_server2.py" not in text
    assert ".github/scripts/run_blender_e2e.py" in text
    assert ".github/scripts/start_mcp_server2.py" in text
    assert "pytest.main" in runner
    assert "os._exit(main())" in runner


def test_windows_e2e_targets_vs2026_runner_explicitly():
    text = E2E_WORKFLOW.read_text(encoding="utf-8")

    assert "runner: windows-2025-vs2026" in text
    assert "runner: windows-latest" not in text
