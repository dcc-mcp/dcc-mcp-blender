"""Unit tests for the ``DCC_MCP_BLENDER_*`` env-var resolvers in ``_env``."""

from __future__ import annotations

import pytest

from dcc_mcp_blender import _env


@pytest.fixture(autouse=True)
def _clear_opt_outs(monkeypatch):
    """Ensure the opt-out vars are unset unless a test sets them explicitly."""
    monkeypatch.delenv(_env.ENV_DISABLE_ARBITRARY_SCRIPT, raising=False)
    monkeypatch.delenv(_env.ENV_DISABLE_EXECUTE_PYTHON, raising=False)


class TestResolveExecutePythonOptOuts:
    def test_no_vars_means_no_opt_out(self):
        assert _env.resolve_execute_python_opt_outs() == ()
        assert _env.resolve_execute_python_disabled() is False

    def test_disable_execute_python_only(self, monkeypatch):
        monkeypatch.setenv(_env.ENV_DISABLE_EXECUTE_PYTHON, "1")
        assert _env.resolve_execute_python_opt_outs() == (_env.ENV_DISABLE_EXECUTE_PYTHON,)
        assert _env.resolve_execute_python_disabled() is True

    def test_disable_arbitrary_script_only(self, monkeypatch):
        monkeypatch.setenv(_env.ENV_DISABLE_ARBITRARY_SCRIPT, "1")
        assert _env.resolve_execute_python_opt_outs() == (_env.ENV_DISABLE_ARBITRARY_SCRIPT,)
        assert _env.resolve_execute_python_disabled() is True

    def test_both_vars_report_both(self, monkeypatch):
        monkeypatch.setenv(_env.ENV_DISABLE_ARBITRARY_SCRIPT, "true")
        monkeypatch.setenv(_env.ENV_DISABLE_EXECUTE_PYTHON, "1")
        assert set(_env.resolve_execute_python_opt_outs()) == {
            _env.ENV_DISABLE_ARBITRARY_SCRIPT,
            _env.ENV_DISABLE_EXECUTE_PYTHON,
        }

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
    def test_falsy_values_do_not_disable(self, monkeypatch, value):
        monkeypatch.setenv(_env.ENV_DISABLE_EXECUTE_PYTHON, value)
        monkeypatch.setenv(_env.ENV_DISABLE_ARBITRARY_SCRIPT, value)
        assert _env.resolve_execute_python_disabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on"])
    def test_truthy_values_disable(self, monkeypatch, value):
        monkeypatch.setenv(_env.ENV_DISABLE_EXECUTE_PYTHON, value)
        assert _env.resolve_execute_python_disabled() is True


class TestGuardArbitraryExecution:
    def test_returns_none_when_execution_allowed(self):
        from dcc_mcp_blender._script_guard import guard_arbitrary_execution

        assert guard_arbitrary_execution("execute_python") is None

    def test_returns_refusal_when_disabled(self, monkeypatch):
        from dcc_mcp_blender._script_guard import (
            ERROR_ARBITRARY_EXECUTION_DISABLED,
            guard_arbitrary_execution,
        )

        monkeypatch.setenv(_env.ENV_DISABLE_ARBITRARY_SCRIPT, "1")
        refusal = guard_arbitrary_execution("execute_python")

        assert refusal is not None
        assert refusal["success"] is False
        assert refusal["error"] == ERROR_ARBITRARY_EXECUTION_DISABLED
        assert "execute_python" in refusal["message"]
        assert refusal["context"]["disabled_by"] == [_env.ENV_DISABLE_ARBITRARY_SCRIPT]
        assert any(
            _env.ENV_DISABLE_ARBITRARY_SCRIPT in solution for solution in refusal["context"]["possible_solutions"]
        )
