"""Regression tests for the configurable main-thread dispatch timeout budget.

Issue #287 reported that ``affinity='main'`` tools (``import_fbx`` among them)
timed out over MCP. The executor/pump wiring was already fixed on ``main``; the
remaining gap was the *budget*: bundled tools declare ``timeout_hint_secs: 0``,
which ``BlenderUiDispatcher`` maps to a hard-coded ``timeout_ms=30000`` with no
way for an operator to raise it. A long import/bake that legitimately needs more
than 30 s therefore still fails with the same timeout symptom.

These tests pin the resolution order (explicit > env > 30 s default) and verify
the resolved budget reaches the default dispatcher actually used by the server.
Real GUI Blender acceptance is still a separate, manually run lane.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dcc_mcp_blender import _env
from dcc_mcp_blender.dispatcher import create_dispatcher
from dcc_mcp_blender.host import BlenderUiDispatcher
from dcc_mcp_blender.server import BlenderMcpServer, BlenderServerOptions


class _FakeTimers:
    """Stand-in for ``bpy.app.timers``; construction only needs registration."""

    def __init__(self) -> None:
        self.registered = []

    def register(self, fn, first_interval: float = 0.0, persistent: bool = False) -> None:
        self.registered.append(fn)

    def unregister(self, fn) -> bool:
        if fn in self.registered:
            self.registered.remove(fn)
            return True
        return False

    def is_registered(self, fn) -> bool:
        return fn in self.registered


def _gui_bpy() -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(background=False, version_string="5.2.2", timers=_FakeTimers()))


# ── Budget resolution (pure) ──────────────────────────────────────────────────


def test_resolver_falls_back_to_30s_default():
    assert _env.resolve_main_thread_timeout_ms(env={}) == _env.DEFAULT_MAIN_THREAD_TIMEOUT_MS == 30000


def test_resolver_reads_env_var():
    assert _env.resolve_main_thread_timeout_ms(env={_env.ENV_MAIN_THREAD_TIMEOUT_MS: "120000"}) == 120000


def test_resolver_explicit_override_wins_over_env():
    assert _env.resolve_main_thread_timeout_ms(60000, env={_env.ENV_MAIN_THREAD_TIMEOUT_MS: "120000"}) == 60000


@pytest.mark.parametrize("bad", ["", "abc", "0", "-5", "12.5"])
def test_resolver_ignores_invalid_env_value(bad):
    assert _env.resolve_main_thread_timeout_ms(env={_env.ENV_MAIN_THREAD_TIMEOUT_MS: bad}) == 30000


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "100"])
def test_validator_rejects_non_positive_int(bad):
    with pytest.raises(ValueError, match="positive integer"):
        _env.validate_main_thread_timeout_ms(bad)


def test_options_reject_invalid_budget():
    with pytest.raises(ValueError, match="positive integer"):
        BlenderServerOptions(main_thread_timeout_ms=0)


# ── Factory propagation ───────────────────────────────────────────────────────


@pytest.mark.parametrize("ui_mode", [True, False])
def test_create_dispatcher_propagates_budget(ui_mode):
    dispatcher = create_dispatcher(ui_mode=ui_mode, timeout_ms=90000)
    assert dispatcher.timeout_ms == 90000


def test_tool_timeout_hint_still_overrides_configured_default():
    dispatcher = BlenderUiDispatcher(timeout_ms=120000)
    assert dispatcher._timeout_ms_from_hint(None) == 120000
    assert dispatcher._timeout_ms_from_hint(0) == 120000
    assert dispatcher._timeout_ms_from_hint(5) == 5000


# ── End-to-end: the resolved budget reaches the server's dispatcher ───────────


def test_default_gui_dispatcher_uses_30s_budget():
    with patch.dict(sys.modules, {"bpy": _gui_bpy()}):
        server = BlenderMcpServer(port=0, gateway_port=0, enable_gateway_failover=False)
        try:
            assert isinstance(server._pump_dispatcher, BlenderUiDispatcher)
            assert server._pump_dispatcher.timeout_ms == 30000
        finally:
            server.stop()


def test_explicit_budget_reaches_default_gui_dispatcher():
    with patch.dict(sys.modules, {"bpy": _gui_bpy()}):
        server = BlenderMcpServer(
            port=0,
            gateway_port=0,
            enable_gateway_failover=False,
            main_thread_timeout_ms=120000,
        )
        try:
            assert server._pump_dispatcher.timeout_ms == 120000
        finally:
            server.stop()


def test_env_budget_reaches_default_gui_dispatcher(monkeypatch):
    monkeypatch.setenv(_env.ENV_MAIN_THREAD_TIMEOUT_MS, "180000")
    with patch.dict(sys.modules, {"bpy": _gui_bpy()}):
        server = BlenderMcpServer(port=0, gateway_port=0, enable_gateway_failover=False)
        try:
            assert server._pump_dispatcher.timeout_ms == 180000
        finally:
            server.stop()


def test_explicit_dispatcher_is_not_overridden_by_budget():
    supplied = BlenderUiDispatcher(timeout_ms=45000)
    options = BlenderServerOptions(
        port=0,
        dispatcher=supplied,
        main_thread_timeout_ms=120000,
    )
    with patch.dict(sys.modules, {"bpy": _gui_bpy()}):
        server = BlenderMcpServer(options=options)
        try:
            # A caller-supplied dispatcher owns its own budget; the knob must
            # not replace it or raise while resolving.
            assert server._pump_dispatcher is supplied
            assert server._pump_dispatcher.timeout_ms == 45000
        finally:
            server.stop()
