"""Tests for the BlenderHost adapter."""

from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class _TickOutcome:
    more_pending = False


class _Dispatcher:
    def __init__(self) -> None:
        self.shutdown_called = False
        self.tick_calls = 0

    def tick(self, max_jobs):
        self.tick_calls += 1
        return _TickOutcome()

    def shutdown(self):
        self.shutdown_called = True

    def is_shutdown(self):
        return self.shutdown_called


def _mock_bpy(background: bool = False):
    registered = []

    timers = MagicMock()
    timers.register.side_effect = lambda fn, **kwargs: registered.append((fn, kwargs))
    timers.is_registered.side_effect = lambda fn: any(item[0] is fn for item in registered)

    def unregister(fn):
        registered[:] = [item for item in registered if item[0] is not fn]

    timers.unregister.side_effect = unregister

    bpy = SimpleNamespace(
        app=SimpleNamespace(
            background=background,
            timers=timers,
        )
    )
    return bpy, registered


def test_blender_host_uses_bpy_background_flag():
    from dcc_mcp_blender.host import BlenderHost

    bpy, _registered = _mock_bpy(background=True)
    with patch.dict(sys.modules, {"bpy": bpy}):
        assert BlenderHost(_Dispatcher()).is_background() is True


def test_blender_host_attaches_and_detaches_timer():
    from dcc_mcp_blender.host import BlenderHost

    bpy, registered = _mock_bpy(background=False)
    dispatcher = _Dispatcher()
    host = BlenderHost(dispatcher)

    with patch.dict(sys.modules, {"bpy": bpy}):
        host.start()
        assert host.is_running
        assert len(registered) == 1
        tick_fn, kwargs = registered[0]
        assert kwargs == {"first_interval": 0.0, "persistent": True}

        tick_fn()
        assert dispatcher.tick_calls == 1
        assert host.tick_thread_ident == threading.get_ident()

        host.stop()
        assert not host.is_running
        assert registered == []
        assert dispatcher.shutdown_called is True


def test_blender_callable_dispatcher_posts_work_to_tick_loop():
    from dcc_mcp_blender.host import BlenderCallableDispatcher

    dispatcher = BlenderCallableDispatcher()
    result = []

    def worker():
        result.append(dispatcher.dispatch_callable(lambda: "done"))

    thread = threading.Thread(target=worker)
    thread.start()

    while thread.is_alive() and not result:
        dispatcher.tick(1)

    thread.join(timeout=1)
    assert result == ["done"]


def test_blender_ui_dispatcher_uses_core_queue_and_timer_pump():
    from dcc_mcp_core._server.host_ui_dispatcher import HostUiDispatcherBase

    from dcc_mcp_blender.host import BlenderUiDispatcher

    bpy, registered = _mock_bpy(background=False)
    with patch.dict(sys.modules, {"bpy": bpy}):
        dispatcher = BlenderUiDispatcher(timeout_ms=1000, idle_interval_secs=0.25)
        assert isinstance(dispatcher, HostUiDispatcherBase)

        result = []

        def worker():
            result.append(dispatcher.dispatch_callable(lambda: "done", action_name="test"))

        thread = threading.Thread(target=worker)
        thread.start()

        for _ in range(50):
            if registered:
                break
            time.sleep(0.01)

        assert len(registered) == 1
        tick_fn, kwargs = registered[0]
        assert kwargs == {"first_interval": 0.0, "persistent": True}

        interval = tick_fn()
        thread.join(timeout=1)

        assert result == ["done"]
        assert interval == 0.25
        assert dispatcher.pending_count() == 0
        assert dispatcher.active_count() == 0
        assert dispatcher.pump.tick_thread_ident == threading.get_ident()

        dispatcher.stop()
        assert registered == []


def test_blender_ui_dispatcher_shutdown_unblocks_pending_main_thread_work():
    from dcc_mcp_blender.host import BlenderUiDispatcher

    bpy, registered = _mock_bpy(background=False)
    with patch.dict(sys.modules, {"bpy": bpy}):
        dispatcher = BlenderUiDispatcher(timeout_ms=5000)
        errors = []

        def worker():
            try:
                dispatcher.dispatch_callable(lambda: "never", action_name="blocked")
            except RuntimeError as exc:
                errors.append(str(exc))

        thread = threading.Thread(target=worker)
        thread.start()

        for _ in range(50):
            if registered and dispatcher.pending_count() == 1:
                break
            time.sleep(0.01)

        assert dispatcher.pending_count() == 1
        assert dispatcher.shutdown() == 1
        thread.join(timeout=1)

        assert errors == ["Interrupted"]
        dispatcher.stop_pump()
        assert registered == []
