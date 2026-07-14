"""Unit tests for blender-scripting skill scripts (bpy mocked)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from tests.conftest import load_and_call, make_mock_bpy


def test_scripting_tools_publish_ci_safe_input_contracts():
    tools_path = Path("src/dcc_mcp_blender/skills/blender-scripting/tools.yaml")
    tools = {tool["name"]: tool for tool in yaml.safe_load(tools_path.read_text(encoding="utf-8"))["tools"]}

    execute_python = tools["execute_python"]["input_schema"]
    assert execute_python["required"] == ["code"]
    assert execute_python["properties"]["code"]["minLength"] == 1
    assert execute_python["additionalProperties"] is False

    execute_file = tools["execute_script_file"]["input_schema"]
    assert execute_file["required"] == ["filepath"]
    assert execute_file["properties"]["filepath"]["type"] == "string"

    assert tools["get_blender_info"]["input_schema"]["properties"] == {}


class TestExecutePython:
    def test_simple_code_succeeds(self):
        bpy = make_mock_bpy()
        result = load_and_call(
            "blender-scripting/scripts/execute_python.py",
            bpy,
            code="x = 1 + 1",
        )
        assert result["success"] is True

    def test_stdout_captured(self):
        bpy = make_mock_bpy()
        result = load_and_call(
            "blender-scripting/scripts/execute_python.py",
            bpy,
            code="print('hello world')",
        )
        assert result["success"] is True
        assert "hello world" in result["context"]["stdout"]

    def test_result_variable_returned(self):
        bpy = make_mock_bpy()
        result = load_and_call(
            "blender-scripting/scripts/execute_python.py",
            bpy,
            code="result = 42",
        )
        assert result["success"] is True
        assert result["context"]["result"] == "42"

    def test_syntax_error_returns_failure(self):
        bpy = make_mock_bpy()
        result = load_and_call(
            "blender-scripting/scripts/execute_python.py",
            bpy,
            code="this is not valid python !!!",
        )
        assert result["success"] is False

    def test_runtime_error_returns_failure(self):
        bpy = make_mock_bpy()
        result = load_and_call(
            "blender-scripting/scripts/execute_python.py",
            bpy,
            code="raise ValueError('test error')",
        )
        assert result["success"] is False
        assert "ValueError" in result["context"].get("stderr", "") or "test error" in str(result)

    def test_context_variables_injected(self):
        bpy = make_mock_bpy()
        result = load_and_call(
            "blender-scripting/scripts/execute_python.py",
            bpy,
            code="result = my_var * 2",
            context={"my_var": 21},
        )
        assert result["success"] is True
        assert result["context"]["result"] == "42"

    def test_stderr_captured_on_success(self):
        bpy = make_mock_bpy()
        result = load_and_call(
            "blender-scripting/scripts/execute_python.py",
            bpy,
            code="import sys\nprint('warn', file=sys.stderr)\nresult = 'ok'",
        )

        assert result["success"] is True
        assert result["context"]["stderr"] == "warn\n"
        assert result["context"]["result"] == "ok"

    def test_execution_namespace_exposes_bpy(self):
        bpy = make_mock_bpy(app_attrs={"version_string": "4.3.2"})
        result = load_and_call(
            "blender-scripting/scripts/execute_python.py",
            bpy,
            code="result = bpy.app.version_string",
        )

        assert result["success"] is True
        assert result["context"]["result"] == "4.3.2"


class TestExecuteScriptFile:
    def test_executes_valid_script(self):
        bpy = make_mock_bpy()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("print('from file')\n")
            fpath = f.name

        result = load_and_call(
            "blender-scripting/scripts/execute_script_file.py",
            bpy,
            filepath=fpath,
        )
        assert result["success"] is True
        assert "from file" in result["context"]["stdout"]

    def test_missing_file_returns_error(self):
        bpy = make_mock_bpy()
        result = load_and_call(
            "blender-scripting/scripts/execute_script_file.py",
            bpy,
            filepath="/nonexistent/script.py",
        )
        assert result["success"] is False

    def test_script_exception_returns_failure(self):
        bpy = make_mock_bpy()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("raise RuntimeError('script error')\n")
            fpath = f.name

        result = load_and_call(
            "blender-scripting/scripts/execute_script_file.py",
            bpy,
            filepath=fpath,
        )
        assert result["success"] is False


class TestGetBlenderInfo:
    def test_returns_version_fields(self):
        bpy = make_mock_bpy(
            app_attrs={
                "version": (4, 1, 0),
                "version_string": "4.1.0",
                "binary_path": "/usr/bin/blender",
                "background": True,
            }
        )
        result = load_and_call("blender-scripting/scripts/get_blender_info.py", bpy)
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["blender_version"] == "4.1.0"
        assert ctx["binary_path"] == "/usr/bin/blender"
        assert ctx["is_background"] is True

    def test_python_version_present(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-scripting/scripts/get_blender_info.py", bpy)
        assert result["success"] is True
        assert "python_version" in result["context"]
