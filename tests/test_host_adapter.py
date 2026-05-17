"""Tests for the BlenderHost adapter."""

from __future__ import annotations

import sys
import threading
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
