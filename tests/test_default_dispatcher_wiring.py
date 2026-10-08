"""Regression tests for the default-dispatcher wiring.

Two separate defects previously made every ``affinity='main'`` tool unusable
inside Blender's GUI, while headless kept working:

1. ``BlenderMcpServer.is_background`` did not exist. The default-dispatcher
   branch in ``__init__`` calls it, so it raised ``AttributeError``; the
   surrounding ``except Exception`` swallowed that at debug level and no
   dispatcher or execution bridge was ever created.

2. Even with a dispatcher built, dcc-mcp-core replaces the server's dispatcher
   reference with ``BlenderInlineCallableDispatcher``, which exposes no
   ``start()``/``start_pump()``. ``start()`` therefore had nothing to drive, the
   Blender timer pump was never installed, and queued main-thread work was never
   drained — calls hung until they timed out.

The end-to-end proof (a real GUI Blender serving ``load_skill`` +
``list_objects``) lives in the e2e suite; these tests pin the contracts that
broke, so the regressions cannot return unnoticed.

CI has no GUI lane — every ``"$BLENDER_BIN"`` invocation in
``.github/workflows/e2e.yml`` passes ``--background`` — so the timer-pump path
is only ever exercised here: :class:`TestPumpLifecycle` drives the real
``BlenderMcpServer.start()`` / ``stop()`` against a stub ``bpy.app.timers``
rather than pinning the wiring by inspection.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

from dcc_mcp_core.server_base import DccServerBase

from dcc_mcp_blender.host import BlenderInlineCallableDispatcher, BlenderUiDispatcher
from dcc_mcp_blender.server import BlenderMcpServer


def _fake_bpy(background: bool) -> SimpleNamespace:
    """A minimal ``bpy`` stub exposing only what the code under test reads."""
    return SimpleNamespace(app=SimpleNamespace(background=background))


class TestIsBackground:
    """``__init__`` depends on this before ``super().__init__()`` runs."""

    def test_method_exists(self):
        # The original bug: this attribute was simply absent, and the
        # AttributeError was swallowed. Assert the contract directly.
        assert hasattr(BlenderMcpServer, "is_background")
        assert callable(BlenderMcpServer.is_background)

    def test_reflects_bpy_background_flag(self):
        with patch.dict(sys.modules, {"bpy": _fake_bpy(background=True)}):
            assert BlenderMcpServer.is_background(object()) is True

        with patch.dict(sys.modules, {"bpy": _fake_bpy(background=False)}):
            assert BlenderMcpServer.is_background(object()) is False

    def test_missing_bpy_reports_non_interactive(self):
        # Off-host (no bpy at all) must resolve to a non-interactive default
        # rather than raising.
        with patch.dict(sys.modules, {"bpy": None}):
            assert BlenderMcpServer.is_background(object()) is True


class TestPumpOwnerContract:
    """``start()`` must drive the object that actually owns the timer pump."""

    def test_ui_dispatcher_exposes_pump_lifecycle(self):
        dispatcher = BlenderUiDispatcher()
        # These are what start()/stop() look for.
        assert callable(getattr(dispatcher, "start", None))
        assert callable(getattr(dispatcher, "stop", None))
        assert callable(getattr(dispatcher, "start_pump", None))
        assert callable(getattr(dispatcher, "stop_pump", None))

    def test_inline_wrapper_exposes_no_start(self):
        # This is precisely why the adapter must retain the original
        # dispatcher: core swaps in this wrapper, which cannot start the pump.
        wrapper = BlenderInlineCallableDispatcher(BlenderUiDispatcher().host_dispatcher)
        assert getattr(wrapper, "start", None) is None
        assert getattr(wrapper, "start_pump", None) is None

    def test_server_retains_a_pump_owner_distinct_from_inline_wrapper(self):
        """The retained dispatcher must be the pump-owning one, not the wrapper."""
        ui_dispatcher = BlenderUiDispatcher()

        # Mirror what __init__ stores when it builds the default dispatcher.
        server = object.__new__(BlenderMcpServer)
        server._pump_dispatcher = ui_dispatcher
        server._blender_dispatcher = BlenderInlineCallableDispatcher(ui_dispatcher.host_dispatcher)

        pump_owner = getattr(server, "_pump_dispatcher", None) or server._blender_dispatcher
        assert pump_owner is ui_dispatcher
        assert callable(getattr(pump_owner, "start", None))


class _FakeTimers:
    """Stand-in for ``bpy.app.timers`` that records what the pump registers."""

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


class TestPumpLifecycle:
    """Defect 2, end to end: ``start()`` must install the pump on Blender's timer API.

    This is the assertion the original patch was missing. Reverting ``start()`` to
    drive ``self._blender_dispatcher`` (core's inline wrapper, which exposes no
    ``start()``) or dropping the retained ``_pump_dispatcher`` from ``__init__``
    leaves this test failing with 0 registered timers, so both regressions are
    caught even though no CI lane runs a GUI Blender.
    """

    def test_start_installs_the_host_timer_pump(self):
        timers = _FakeTimers()
        fake_bpy = SimpleNamespace(app=SimpleNamespace(background=False, version_string="4.2.0", timers=timers))

        with patch.dict(sys.modules, {"bpy": fake_bpy}):
            # Interactive mode, so __init__ builds the UI dispatcher itself.
            server = BlenderMcpServer(port=0, gateway_port=0, enable_gateway_failover=False)

            # Core swapped its inline wrapper in; the retained pump owner must
            # not be that wrapper, otherwise the assertions below prove nothing.
            assert type(server._blender_dispatcher).__name__ == "BlenderInlineCallableDispatcher"
            assert server._pump_dispatcher is not server._blender_dispatcher

            pump = server._pump_dispatcher.pump
            assert pump.is_installed is False

            # Patch only core's lifecycle so no HTTP server is bound and no
            # atexit hook is installed; the adapter's own start()/stop() — the
            # code under test — runs for real.
            with patch.object(DccServerBase, "start", lambda self, *args, **kwargs: None), patch.object(
                DccServerBase, "stop", lambda self, *args, **kwargs: None
            ):
                server.start(install_atexit_hook=False)
                try:
                    assert len(timers.registered) == 1, "start() registered no Blender timer"
                    assert pump.is_installed is True
                finally:
                    server.stop()

            assert timers.registered == []
            assert pump.is_installed is False
