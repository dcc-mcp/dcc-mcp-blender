"""Tests for BlenderMcpServer and module-level helpers."""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────


def _builtin_skills_dir() -> str:
    from pathlib import Path

    return str(Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills")


# ── BlenderMcpServer unit tests ───────────────────────────────────────────────


class TestBlenderMcpServerBasic:
    def test_instantiation(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        assert server is not None

    def test_default_port(self):
        from dcc_mcp_blender.server import DEFAULT_PORT, BlenderMcpServer

        server = BlenderMcpServer()
        assert server.port == DEFAULT_PORT

    def test_explicit_zero_port_overrides_environment(self, monkeypatch):
        from dcc_mcp_blender.server import BlenderServerOptions

        monkeypatch.setenv("DCC_MCP_BLENDER_PORT", "18765")
        assert BlenderServerOptions(port=0).to_core_options().port == 0

    def test_custom_port(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=19999)
        assert server.port == 19999

    def test_extra_skill_paths_stored(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(extra_skill_paths=["/tmp/extra"])
        assert "/tmp/extra" in server._extra_skill_paths

    def test_not_running_initially(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer()
        assert not server.is_running

    def test_mcp_url_none_when_not_running(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer()
        assert server.mcp_url is None

    def test_dispatcher_is_wrapped_as_execution_bridge(self):
        from dcc_mcp_blender.host import BlenderCallableDispatcher, BlenderInlineCallableDispatcher
        from dcc_mcp_blender.server import BlenderMcpServer

        dispatcher = BlenderCallableDispatcher()
        server = BlenderMcpServer(port=0, dispatcher=dispatcher)

        mode = server._options.execution.mode
        assert getattr(mode, "kind", None) == "bridge"
        assert isinstance(mode.bridge.dispatcher, BlenderInlineCallableDispatcher)
        assert mode.bridge.host_dispatcher is dispatcher.host_dispatcher
        assert mode.bridge.dispatch_callable(lambda: "ok") == "ok"

    def test_core_backed_ui_dispatcher_is_used_as_execution_bridge(self):
        from dcc_mcp_blender.host import BlenderInlineCallableDispatcher, BlenderUiDispatcher
        from dcc_mcp_blender.server import BlenderMcpServer

        dispatcher = BlenderUiDispatcher()
        server = BlenderMcpServer(port=0, dispatcher=dispatcher)

        mode = server._options.execution.mode
        assert getattr(mode, "kind", None) == "bridge"
        # The UI dispatcher now carries a host_dispatcher (QueueDispatcher)
        # so the bridge uses BlenderInlineCallableDispatcher for the hop
        assert isinstance(mode.bridge.dispatcher, BlenderInlineCallableDispatcher)
        assert mode.bridge.host_dispatcher is dispatcher.host_dispatcher
        assert mode.bridge.dispatch_callable(lambda: "ok", thread_affinity="main") == "ok"

    def test_explicit_execution_bridge_takes_precedence(self):
        from dcc_mcp_core import HostExecutionBridge

        from dcc_mcp_blender.host import BlenderCallableDispatcher
        from dcc_mcp_blender.server import BlenderMcpServer

        dispatcher = BlenderCallableDispatcher()
        bridge = HostExecutionBridge(dispatcher=dispatcher)
        server = BlenderMcpServer(
            port=0,
            dispatcher=BlenderCallableDispatcher(),
            execution_bridge=bridge,
        )

        mode = server._options.execution.mode
        assert getattr(mode, "kind", None) == "bridge"
        assert mode.bridge is bridge


class TestGatewayRemotePublicOptions:
    """Remote bind policy stays explicit on the public Core options route."""

    @pytest.fixture(autouse=True)
    def _clear_remote_environment(self, monkeypatch):
        monkeypatch.delenv("DCC_MCP_GATEWAY_REMOTE_HOST", raising=False)
        monkeypatch.delenv("DCC_MCP_GATEWAY_REMOTE_PORT", raising=False)

    @pytest.mark.parametrize(
        "remote_options",
        [
            {"gateway_remote_port": 0},
            {"gateway_remote_port": 65535},
            {"gateway_remote_host": "127.0.0.1"},
            {"gateway_remote_host": "::1", "gateway_remote_port": 1},
            {"gateway_remote_host": "private.internal", "gateway_remote_port": 0},
        ],
    )
    def test_explicit_values_forward_to_supported_public_factory(self, monkeypatch, remote_options):
        from dcc_mcp_blender import server as srv_mod

        omitted = object()
        calls = []
        core_options = object()

        def from_env(*, gateway_remote_host=omitted, gateway_remote_port=omitted, **kwargs):
            if gateway_remote_host is not omitted:
                kwargs["gateway_remote_host"] = gateway_remote_host
            if gateway_remote_port is not omitted:
                kwargs["gateway_remote_port"] = gateway_remote_port
            calls.append(kwargs)
            return core_options

        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=from_env))
        options = srv_mod.BlenderServerOptions(gateway_port=19765, registry_dir="private-registry", **remote_options)

        assert options.to_core_options() is core_options
        assert len(calls) == 1
        assert calls[0]["gateway_port"] == 19765
        assert calls[0]["registry_dir"] == "private-registry"
        assert {key: value for key, value in calls[0].items() if key.startswith("gateway_remote_")} == remote_options

    def test_omitted_values_preserve_legacy_public_factory(self, monkeypatch):
        from dcc_mcp_blender import server as srv_mod

        calls = []

        def legacy_from_env(**kwargs):
            calls.append(kwargs)
            return "legacy-options"

        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=legacy_from_env))
        options = srv_mod.BlenderServerOptions(gateway_remote_host=None, gateway_remote_port=None)

        assert options.to_core_options() == "legacy-options"
        assert len(calls) == 1
        assert "gateway_remote_host" not in calls[0]
        assert "gateway_remote_port" not in calls[0]

    @pytest.mark.parametrize(
        "remote_options",
        [{"gateway_remote_host": "127.0.0.1"}, {"gateway_remote_port": 0}],
    )
    def test_explicit_values_fail_closed_for_kwargs_only_core(self, monkeypatch, remote_options):
        from dcc_mcp_blender import server as srv_mod

        calls = []

        def legacy_from_env(**kwargs):
            calls.append(kwargs)
            return "silently-ignored-policy"

        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=legacy_from_env))
        with pytest.raises(RuntimeError):
            srv_mod.BlenderServerOptions(**remote_options).to_core_options()
        assert calls == []

    def test_partial_core_capability_does_not_silently_drop_port(self, monkeypatch):
        from dcc_mcp_blender import server as srv_mod

        calls = []

        def host_only_from_env(*, gateway_remote_host=None, **kwargs):
            calls.append((gateway_remote_host, kwargs))

        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=host_only_from_env))
        with pytest.raises(RuntimeError):
            srv_mod.BlenderServerOptions(gateway_remote_host="127.0.0.1", gateway_remote_port=0).to_core_options()
        assert calls == []

    @pytest.mark.parametrize("error_type", [TypeError, ValueError])
    def test_uninspectable_core_capability_fails_closed(self, monkeypatch, error_type):
        from unittest.mock import MagicMock

        from dcc_mcp_blender import server as srv_mod

        factory = MagicMock()
        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=factory))
        error = error_type("public signature unavailable")
        monkeypatch.setattr(srv_mod.inspect, "signature", MagicMock(side_effect=error))

        with pytest.raises(RuntimeError, match="Cannot verify") as result:
            srv_mod.BlenderServerOptions(gateway_remote_port=0).to_core_options()
        assert result.value.__cause__ is error
        factory.assert_not_called()

    def test_installed_legacy_core_signature_rejects_explicit_remote_before_factory(self, monkeypatch):
        import functools
        import inspect

        from dcc_mcp_core import DccServerOptions

        from dcc_mcp_blender import server as srv_mod

        original_factory = DccServerOptions.from_env
        if "gateway_remote_port" in inspect.signature(original_factory).parameters:
            pytest.skip("Installed Core already publishes gateway_remote_port")

        calls = []

        @functools.wraps(original_factory)
        def observed_factory(*args, **kwargs):
            calls.append((args, kwargs))
            pytest.fail("A legacy Core factory must not receive an explicit remote policy")

        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=observed_factory))
        with pytest.raises(RuntimeError, match="lacks public remote"):
            srv_mod.BlenderServerOptions(gateway_remote_port=0).to_core_options()
        assert calls == []

    @pytest.mark.parametrize(
        ("env_key", "env_value"),
        [
            ("DCC_MCP_GATEWAY_REMOTE_HOST", "127.0.0.1"),
            ("DCC_MCP_GATEWAY_REMOTE_HOST", ""),
            ("DCC_MCP_GATEWAY_REMOTE_HOST", " "),
            ("DCC_MCP_GATEWAY_REMOTE_PORT", "0"),
            ("DCC_MCP_GATEWAY_REMOTE_PORT", ""),
            ("DCC_MCP_GATEWAY_REMOTE_PORT", "invalid"),
        ],
    )
    def test_environment_remote_policy_fails_closed_for_legacy_core(self, monkeypatch, env_key, env_value):
        from dcc_mcp_blender import server as srv_mod

        calls = []

        def legacy_from_env(**kwargs):
            calls.append(kwargs)

        monkeypatch.setenv(env_key, env_value)
        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=legacy_from_env))
        with pytest.raises(RuntimeError):
            srv_mod.BlenderServerOptions().to_core_options()
        assert calls == []

    @pytest.mark.parametrize(
        ("env_key", "env_value", "remote_key"),
        [
            ("DCC_MCP_GATEWAY_REMOTE_HOST", "127.0.0.1", "gateway_remote_host"),
            ("DCC_MCP_GATEWAY_REMOTE_HOST", "", "gateway_remote_host"),
            ("DCC_MCP_GATEWAY_REMOTE_HOST", " ", "gateway_remote_host"),
            ("DCC_MCP_GATEWAY_REMOTE_PORT", "0", "gateway_remote_port"),
            ("DCC_MCP_GATEWAY_REMOTE_PORT", "", "gateway_remote_port"),
            ("DCC_MCP_GATEWAY_REMOTE_PORT", "invalid", "gateway_remote_port"),
        ],
    )
    def test_capable_core_resolves_environment_policy_from_none(self, monkeypatch, env_key, env_value, remote_key):
        from dcc_mcp_blender import server as srv_mod

        omitted = object()
        calls = []

        def from_env(*, gateway_remote_host=omitted, gateway_remote_port=omitted, **kwargs):
            calls.append({"gateway_remote_host": gateway_remote_host, "gateway_remote_port": gateway_remote_port})
            return "core-resolves-environment"

        monkeypatch.setenv(env_key, env_value)
        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=from_env))

        assert srv_mod.BlenderServerOptions().to_core_options() == "core-resolves-environment"
        assert calls[0][remote_key] is None
        other_key = "gateway_remote_host" if remote_key == "gateway_remote_port" else "gateway_remote_port"
        assert calls[0][other_key] is omitted
        assert os.environ[env_key] == env_value

    def test_explicit_zero_port_overrides_remote_environment(self, monkeypatch):
        from dcc_mcp_blender import server as srv_mod

        calls = []

        def from_env(*, gateway_remote_port=None, **kwargs):
            calls.append(gateway_remote_port)

        monkeypatch.setenv("DCC_MCP_GATEWAY_REMOTE_PORT", "12345")
        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=from_env))
        srv_mod.BlenderServerOptions(gateway_remote_port=0).to_core_options()
        assert calls == [0]

    @pytest.mark.parametrize("invalid_host_env", ["", " "])
    def test_explicit_host_shields_invalid_host_environment(self, monkeypatch, invalid_host_env):
        from dcc_mcp_blender import server as srv_mod

        calls = []

        def from_env(*, gateway_remote_host=None, **kwargs):
            calls.append(gateway_remote_host)

        monkeypatch.setenv("DCC_MCP_GATEWAY_REMOTE_HOST", invalid_host_env)
        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=from_env))
        srv_mod.BlenderServerOptions(gateway_remote_host="127.0.0.1").to_core_options()
        assert calls == ["127.0.0.1"]

    @pytest.mark.parametrize("invalid_port", [True, False, -1, 65536, 1.0, "0"])
    def test_invalid_remote_port_rejected_before_core(self, monkeypatch, invalid_port):
        from dcc_mcp_blender import server as srv_mod

        calls = []
        monkeypatch.setattr(
            srv_mod, "DccServerOptions", SimpleNamespace(from_env=lambda **kwargs: calls.append(kwargs))
        )
        with pytest.raises((TypeError, ValueError)):
            srv_mod.BlenderServerOptions(gateway_remote_port=invalid_port).to_core_options()
        assert calls == []

    @pytest.mark.parametrize("invalid_host", ["", " ", "\t\n", True, False, 123])
    def test_invalid_remote_host_rejected_before_core(self, monkeypatch, invalid_host):
        from dcc_mcp_blender import server as srv_mod

        calls = []
        monkeypatch.setattr(
            srv_mod, "DccServerOptions", SimpleNamespace(from_env=lambda **kwargs: calls.append(kwargs))
        )
        with pytest.raises((TypeError, ValueError)):
            srv_mod.BlenderServerOptions(gateway_remote_host=invalid_host).to_core_options()
        assert calls == []

    @pytest.mark.parametrize("entrypoint", ["BlenderMcpServer", "start_server"])
    @pytest.mark.parametrize(
        "remote_options",
        [{"gateway_remote_port": True}, {"gateway_remote_host": " "}],
    )
    def test_invalid_public_parameters_rejected_before_dispatcher_or_core(
        self, monkeypatch, entrypoint, remote_options
    ):
        from unittest.mock import MagicMock

        from dcc_mcp_blender import dispatcher
        from dcc_mcp_blender import server as srv_mod

        create_dispatcher = MagicMock(side_effect=AssertionError("No dispatcher should initialize"))
        from_env = MagicMock(side_effect=AssertionError("No Core options should initialize"))
        monkeypatch.setattr(dispatcher, "create_dispatcher", create_dispatcher)
        monkeypatch.setattr(srv_mod, "DccServerOptions", SimpleNamespace(from_env=from_env))
        monkeypatch.setattr(srv_mod, "_server_instance", None)

        with pytest.raises(ValueError):
            getattr(srv_mod, entrypoint)(**remote_options)
        create_dispatcher.assert_not_called()
        from_env.assert_not_called()

    def test_constructor_forwards_explicit_remote_options(self, monkeypatch):
        from dcc_mcp_blender import server as srv_mod

        observed = []

        class _BeforeCoreInitialization(Exception):
            pass

        def capture_options(options):
            observed.append(options)
            raise _BeforeCoreInitialization

        monkeypatch.setattr(srv_mod.BlenderServerOptions, "to_core_options", capture_options)
        with pytest.raises(_BeforeCoreInitialization):
            srv_mod.BlenderMcpServer(
                port=0,
                gateway_port=19765,
                dispatcher=object(),
                gateway_remote_host="127.0.0.1",
                gateway_remote_port=0,
            )
        assert len(observed) == 1
        assert observed[0].gateway_remote_host == "127.0.0.1"
        assert observed[0].gateway_remote_port == 0
        assert observed[0].gateway_port == 19765

    @pytest.mark.parametrize(
        "remote_options",
        [{"gateway_remote_host": "127.0.0.1"}, {"gateway_remote_port": 0}],
    )
    def test_constructor_rejects_options_and_explicit_remote_conflict(self, monkeypatch, remote_options):
        from unittest.mock import MagicMock

        from dcc_mcp_blender import server as srv_mod

        to_core_options = MagicMock()
        monkeypatch.setattr(srv_mod.BlenderServerOptions, "to_core_options", to_core_options)
        with pytest.raises(ValueError, match="BlenderServerOptions"):
            srv_mod.BlenderMcpServer(options=srv_mod.BlenderServerOptions(), **remote_options)
        to_core_options.assert_not_called()

    def test_start_server_forwards_remote_options_preserving_legacy_positionals(self, monkeypatch):
        from unittest.mock import MagicMock

        from dcc_mcp_blender import server as srv_mod

        fake_server = MagicMock()
        factory = MagicMock(return_value=fake_server)
        monkeypatch.setattr(srv_mod, "_server_instance", None)
        monkeypatch.setattr(srv_mod, "BlenderMcpServer", factory)

        result = srv_mod.start_server(
            0,
            None,
            False,
            False,
            False,
            19765,
            "private-registry",
            gateway_remote_host="127.0.0.1",
            gateway_remote_port=0,
        )

        assert result is fake_server
        assert factory.call_args.kwargs["gateway_remote_host"] == "127.0.0.1"
        assert factory.call_args.kwargs["gateway_remote_port"] == 0
        assert factory.call_args.kwargs["gateway_port"] == 19765
        assert factory.call_args.kwargs["registry_dir"] == "private-registry"
        fake_server.start.assert_called_once_with()
        fake_server.register_builtin_actions.assert_not_called()

    @pytest.mark.parametrize(
        "remote_options",
        [{"gateway_remote_host": "127.0.0.1"}, {"gateway_remote_port": 0}],
    )
    def test_running_singleton_rejects_explicit_remote_reconfiguration(self, monkeypatch, remote_options):
        from unittest.mock import MagicMock

        from dcc_mcp_blender import server as srv_mod

        existing = SimpleNamespace(is_running=True)
        factory = MagicMock()
        monkeypatch.setattr(srv_mod, "_server_instance", existing)
        monkeypatch.setattr(srv_mod, "BlenderMcpServer", factory)

        with pytest.raises(RuntimeError):
            srv_mod.start_server(**remote_options)
        assert srv_mod._server_instance is existing
        factory.assert_not_called()

    def test_running_singleton_keeps_default_idempotence(self, monkeypatch):
        from unittest.mock import MagicMock

        from dcc_mcp_blender import server as srv_mod

        existing = SimpleNamespace(is_running=True)
        factory = MagicMock()
        monkeypatch.setattr(srv_mod, "_server_instance", existing)
        monkeypatch.setattr(srv_mod, "BlenderMcpServer", factory)

        assert srv_mod.start_server(gateway_remote_host=None, gateway_remote_port=None) is existing
        factory.assert_not_called()


class TestSkillPathCollection:
    """_collect_skill_paths respects all path sources."""

    def test_builtin_always_included(self):
        from dcc_mcp_blender.server import _BUILTIN_SKILLS_DIR, BlenderMcpServer

        server = BlenderMcpServer()
        paths = server._collect_skill_paths()
        assert str(_BUILTIN_SKILLS_DIR) in paths

    def test_extra_paths_take_priority(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        with tempfile.TemporaryDirectory() as tmp:
            server = BlenderMcpServer(extra_skill_paths=[tmp])
            paths = server._collect_skill_paths()
            assert paths[0] == tmp

    def test_env_var_blender_skill_paths(self):
        from dcc_mcp_blender.server import _ENV_EXTRA_SKILL_PATHS, BlenderMcpServer

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {_ENV_EXTRA_SKILL_PATHS: tmp}):
                server = BlenderMcpServer()
                paths = server._collect_skill_paths()
                assert tmp in paths

    def test_env_var_generic_skill_paths(self):
        from dcc_mcp_blender.server import _ENV_GENERIC_SKILL_PATHS, BlenderMcpServer

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {_ENV_GENERIC_SKILL_PATHS: tmp}):
                server = BlenderMcpServer()
                paths = server._collect_skill_paths()
                assert tmp in paths

    def test_blender_env_before_generic_env(self):
        from dcc_mcp_blender.server import (
            _ENV_EXTRA_SKILL_PATHS,
            _ENV_GENERIC_SKILL_PATHS,
            BlenderMcpServer,
        )

        with tempfile.TemporaryDirectory() as app_tmp, tempfile.TemporaryDirectory() as global_tmp:
            with patch.dict(
                "os.environ",
                {
                    _ENV_EXTRA_SKILL_PATHS: app_tmp,
                    _ENV_GENERIC_SKILL_PATHS: global_tmp,
                },
            ):
                server = BlenderMcpServer()
                paths = server._collect_skill_paths()
                assert app_tmp in paths
                assert global_tmp in paths
                assert paths.index(app_tmp) < paths.index(global_tmp)

    def test_nonexistent_paths_excluded(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(extra_skill_paths=["/nonexistent/path/xyz"])
        paths = server._collect_skill_paths()
        assert "/nonexistent/path/xyz" not in paths

    def test_no_duplicates(self):
        from dcc_mcp_blender.server import _BUILTIN_SKILLS_DIR, BlenderMcpServer

        builtin = str(_BUILTIN_SKILLS_DIR)
        server = BlenderMcpServer(extra_skill_paths=[builtin])
        paths = server._collect_skill_paths()
        assert paths.count(builtin) == 1


class TestServerLifecycle:
    """Start/stop lifecycle tests using a real McpHttpServer."""

    def test_start_and_stop(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        server.start()
        assert server.is_running
        url = server.mcp_url
        assert url is not None
        assert "http://127.0.0.1:" in url
        server.stop()
        assert not server.is_running

    def test_start_idempotent(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        server.start()
        port_before = server.port
        server.start()  # second call should be no-op
        assert server.port == port_before
        server.stop()

    def test_stop_noop_when_not_running(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        server.stop()  # should not raise

    def test_port_updated_after_start(self):
        """port is updated to the actual OS-assigned port when port=0."""
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        server.start()
        try:
            assert server.port != 0, "port should be updated to the assigned port"
            assert server.port > 0
        finally:
            server.stop()

    def test_mcp_url_contains_port(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        server.start()
        try:
            url = server.mcp_url
            assert str(server.port) in url
        finally:
            server.stop()


class TestProgressiveLoading:
    """Progressive skill loading API: discover_skills / load_skill / unload_skill."""

    def test_list_skills_returns_list_before_start(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        # Should return empty list when server not started (no crash)
        assert server.list_skills() == []

    def test_find_skills_returns_list_before_start(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        assert server.find_skills() == []

    def test_discover_skills_returns_zero_before_start(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        assert server.discover_skills() == 0

    def test_loaded_skill_count_before_start(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        assert server.loaded_skill_count() == 0

    def test_is_skill_loaded_before_start(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        assert not server.is_skill_loaded("blender-scene")

    def test_load_skill_returns_false_when_not_discovered(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        assert server.load_skill("blender-scene") is False

    def test_unload_skill_returns_false_when_not_discovered(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        assert server.unload_skill("blender-scene") is False

    def test_list_skills_after_start(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        server.start()
        try:
            skills = server.list_skills()
            assert isinstance(skills, list)
        finally:
            server.stop()

    def test_find_skills_after_start(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        server.start()
        try:
            results = server.find_skills(dcc="blender")
            assert isinstance(results, list)
        finally:
            server.stop()

    # ── behaviour tests (mocked McpHttpServer) ───────────────────────────────

    def _make_server_with_mock(self, mock_inner):
        """Return a running BlenderMcpServer whose inner _server is mock_inner."""
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        server.start()
        server._server = mock_inner  # replace with mock after start
        return server

    def test_list_skills_returns_content(self):
        """list_skills() forwards to _server.list_skills() and returns its value."""
        from unittest.mock import MagicMock

        fake_skills = [
            {"name": "blender-scene", "loaded": True, "dcc": "blender"},
            {"name": "blender-mesh", "loaded": False, "dcc": "blender"},
        ]
        mock_inner = MagicMock()
        mock_inner.list_skills.return_value = fake_skills

        server = self._make_server_with_mock(mock_inner)
        try:
            result = server.list_skills()
            assert result == fake_skills
            mock_inner.list_skills.assert_called_once_with(status=None)
        finally:
            server.stop()

    def test_list_skills_with_status_filter(self):
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.list_skills.return_value = [{"name": "blender-scene", "loaded": True}]

        server = self._make_server_with_mock(mock_inner)
        try:
            server.list_skills(status="loaded")
            mock_inner.list_skills.assert_called_once_with(status="loaded")
        finally:
            server.stop()

    def test_find_skills_forwards_query_and_tags(self):
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.search_skills.return_value = [{"name": "blender-scene"}]

        server = self._make_server_with_mock(mock_inner)
        try:
            result = server.find_skills(query="scene", tags=["blender"], dcc="blender")
            assert result == [{"name": "blender-scene"}]
            mock_inner.search_skills.assert_called_once_with(
                query="scene",
                tags=["blender"],
                dcc="blender",
                scope=None,
                limit=None,
            )
        finally:
            server.stop()

    def test_search_skills_forwards_scope_and_limit(self):
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.search_skills.return_value = [{"name": "blender-scene"}]

        server = self._make_server_with_mock(mock_inner)
        try:
            result = server.search_skills(query="scene", scope="system", limit=3)
            assert result == [{"name": "blender-scene"}]
            mock_inner.search_skills.assert_called_once_with(
                query="scene",
                tags=[],
                dcc="blender",
                scope="system",
                limit=3,
            )
        finally:
            server.stop()

    def test_search_skills_semantic_augmentation_preserves_limit(self):
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.search_skills.return_value = [{"name": "blender-scene"}]
        mock_inner.list_skills.return_value = [{"name": "blender-scene"}]
        server = self._make_server_with_mock(mock_inner)
        semantic = MagicMock()
        semantic.augment.return_value = [{"name": "blender-scene"}]
        server._semantic = semantic
        try:
            result = server.search_skills(query="render", limit=1)
            assert result == [{"name": "blender-scene"}]
            semantic.augment.assert_called_once_with(
                [{"name": "blender-scene"}],
                "render",
                [{"name": "blender-scene"}],
                limit=1,
            )
        finally:
            server.stop()

    def test_find_skills_tags_none_becomes_empty_list(self):
        """tags=None must be coerced to [] so the Rust binding doesn't crash."""
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.search_skills.return_value = []

        server = self._make_server_with_mock(mock_inner)
        try:
            server.find_skills(dcc="blender")  # tags not passed → None
            _call_kwargs = mock_inner.search_skills.call_args
            assert _call_kwargs.kwargs["tags"] == []
        finally:
            server.stop()

    def test_load_skill_returns_actions_and_updates_state(self):
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.load_skill.return_value = ["blender_scene__get_session_info", "blender_scene__list_objects"]
        mock_inner.is_loaded.return_value = True

        server = self._make_server_with_mock(mock_inner)
        try:
            assert server.load_skill("blender-scene") is True
            mock_inner.load_skill.assert_called_once_with("blender-scene")
            # is_skill_loaded now delegates to _server.is_loaded
            assert server.is_skill_loaded("blender-scene") is True
        finally:
            server.stop()

    def test_unload_skill_returns_count(self):
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.unload_skill.return_value = 5
        mock_inner.is_loaded.return_value = False

        server = self._make_server_with_mock(mock_inner)
        try:
            assert server.unload_skill("blender-scene") is True
            mock_inner.unload_skill.assert_called_once_with("blender-scene")
            assert server.is_skill_loaded("blender-scene") is False
        finally:
            server.stop()

    def test_discover_skills_returns_count(self):
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.discover.return_value = 7

        server = self._make_server_with_mock(mock_inner)
        try:
            count = server.discover_skills()
            assert count == 7
        finally:
            server.stop()

    def test_discover_skills_extra_paths_prepended(self):
        """Extra paths passed to discover_skills() appear before built-ins."""
        import tempfile
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.discover.return_value = 2

        server = self._make_server_with_mock(mock_inner)
        try:
            with tempfile.TemporaryDirectory() as extra:
                server.discover_skills(extra_paths=[extra])
                called_paths = mock_inner.discover.call_args.kwargs["extra_paths"]
                assert called_paths[0] == extra
        finally:
            server.stop()

    def test_loaded_skill_count(self):
        from unittest.mock import MagicMock

        mock_inner = MagicMock()
        mock_inner.loaded_count.return_value = 3

        server = self._make_server_with_mock(mock_inner)
        try:
            assert server.loaded_skill_count() == 3
            mock_inner.loaded_count.assert_called_once()
        finally:
            server.stop()

    def test_load_unload_round_trip(self):
        """Full load → unload → reload cycle via mocks."""
        from unittest.mock import MagicMock

        loaded_state = {"blender-scene": False}

        mock_inner = MagicMock()
        mock_inner.load_skill.side_effect = lambda name: (
            loaded_state.__setitem__(name, True) or ["action_a", "action_b"]
        )
        mock_inner.unload_skill.side_effect = lambda name: loaded_state.__setitem__(name, False) or 2
        mock_inner.is_loaded.side_effect = lambda name: loaded_state.get(name, False)
        mock_inner.loaded_count.side_effect = lambda: sum(loaded_state.values())

        server = self._make_server_with_mock(mock_inner)
        try:
            # Load
            assert server.load_skill("blender-scene") is True
            assert server.is_skill_loaded("blender-scene") is True
            assert server.loaded_skill_count() == 1

            # Unload
            assert server.unload_skill("blender-scene") is True
            assert server.is_skill_loaded("blender-scene") is False
            assert server.loaded_skill_count() == 0

            # Reload
            server.load_skill("blender-scene")
            assert server.is_skill_loaded("blender-scene") is True
            assert server.loaded_skill_count() == 1
        finally:
            server.stop()


class TestModuleSingleton:
    """Module-level start_server / stop_server singleton pattern."""

    def setup_method(self):
        # ensure clean state
        from dcc_mcp_blender import server as srv_mod

        srv_mod._server_instance = None

    def teardown_method(self):
        from dcc_mcp_blender import server as srv_mod

        if srv_mod._server_instance is not None:
            srv_mod.stop_server()

    def test_start_stop(self):
        from dcc_mcp_blender.server import get_server, start_server, stop_server

        server = start_server(port=0)
        assert server is not None
        assert get_server() is server
        stop_server()
        assert get_server() is None

    def test_start_idempotent(self):
        from dcc_mcp_blender.server import start_server, stop_server

        s1 = start_server(port=0)
        s2 = start_server(port=0)
        assert s1 is s2
        stop_server()

    def test_get_server_none_when_not_running(self):
        from dcc_mcp_blender.server import get_server

        assert get_server() is None

    def test_stop_noop_when_not_running(self):
        from dcc_mcp_blender.server import stop_server

        stop_server()  # should not raise
        stop_server()  # should not raise
