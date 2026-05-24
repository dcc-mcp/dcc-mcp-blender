"""Tests for BlenderMcpServer and module-level helpers."""

from __future__ import annotations

import tempfile
from unittest.mock import patch

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
