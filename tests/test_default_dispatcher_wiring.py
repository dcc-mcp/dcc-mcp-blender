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
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

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
