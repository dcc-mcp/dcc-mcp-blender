"""Readiness proves host execution and fences callbacks across lifecycles."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from dcc_mcp_core import HostExecutionBridge
from dcc_mcp_core.host import QueueDispatcher

from dcc_mcp_blender._readiness import ReadinessBinder
from dcc_mcp_blender.host import BlenderInlineCallableDispatcher, BlenderUiDispatcher


def _server(**kwargs):
    return SimpleNamespace(_server=SimpleNamespace(set_readiness_probe=lambda probe: None), **kwargs)


def _assert_unready(binder):
    report = binder.report()
    assert report["dcc"] is False
    assert report["main_thread_executor"] is False


class _AsyncDispatcher:
    def __init__(self, response=None):
        self.response = response if response is not None else {"success": True, "status": "pending"}
        self.pending = []

    def submit_async_callable(self, **kwargs):
        self.pending.append(kwargs)
        return self.response

    def complete(self, result, *, execute=True):
        call = self.pending[-1]
        if execute:
            call["task"]()
        call["on_complete"](result)


def test_retained_pump_owner_queues_probe_without_native_blender_access(monkeypatch):
    monkeypatch.setitem(sys.modules, "bpy", None)
    queue = QueueDispatcher()

    def unexpected_async(**kwargs):
        raise AssertionError("readiness must not poke the native timer")

    owner = SimpleNamespace(host_dispatcher=queue, submit_async_callable=unexpected_async)
    binder = ReadinessBinder()
    assert binder.bind(_server(_pump_dispatcher=owner, _blender_dispatcher=object())) is True
    assert binder.bound_dispatcher is owner
    _assert_unready(binder)
    queue.tick(1)
    assert binder.report()["dcc"] is True
    assert binder.report()["main_thread_executor"] is True


def test_explicit_headless_bridge_requires_its_host_queue_to_run():
    queue = QueueDispatcher()
    bridge = HostExecutionBridge(
        dispatcher=BlenderInlineCallableDispatcher(queue), host_dispatcher=queue, default_thread_affinity="main"
    )
    binder = ReadinessBinder()
    assert binder.bind(_server(_execution_bridge=bridge, _blender_dispatcher=bridge.dispatcher)) is True
    assert binder.bound_dispatcher is queue
    _assert_unready(binder)
    queue.tick(1)
    assert binder.report()["dcc"] is True


@pytest.mark.parametrize("drain", ["host_queue", "owner_tick"])
def test_explicit_ui_bridge_requires_the_actual_http_queue(drain, monkeypatch):
    monkeypatch.setitem(sys.modules, "bpy", None)
    owner = BlenderUiDispatcher()
    local_queue = owner.host_dispatcher
    bridge = HostExecutionBridge(dispatcher=owner)
    http_queue = bridge.resolve_host_dispatcher()
    assert http_queue is not local_queue

    binder = ReadinessBinder()
    server = _server(_execution_bridge=bridge, _pump_dispatcher=owner, _blender_dispatcher=owner)
    assert binder.bind(server) is True
    assert binder.bound_dispatcher is http_queue
    local_queue.tick(1)
    _assert_unready(binder)

    if drain == "host_queue":
        http_queue.tick(1)
    else:
        owner._timer_tick()
    assert binder.report()["dcc"] is True
    assert binder.report()["main_thread_executor"] is True


def test_inline_wrapper_without_host_route_cannot_claim_readiness():
    binder = ReadinessBinder()
    assert binder.bind(_server(_blender_dispatcher=object())) is False
    _assert_unready(binder)


def test_bridge_resolution_failure_stays_unready():
    def resolve_host_dispatcher():
        raise RuntimeError("unavailable")

    binder = ReadinessBinder()
    bridge = SimpleNamespace(resolve_host_dispatcher=resolve_host_dispatcher)
    assert binder.bind(_server(_execution_bridge=bridge)) is False
    _assert_unready(binder)


@pytest.mark.parametrize(
    "result",
    [
        {"success": False, "error": "cancelled"},
        {"success": False, "status": "failed"},
        {"success": True, "status": "interrupted"},
        {"success": True, "status": "cancelled"},
        {"success": True, "status": "expired"},
        None,
    ],
)
def test_failed_or_cancelled_probe_outcome_stays_unready(result):
    dispatcher = _AsyncDispatcher()
    binder = ReadinessBinder()
    assert binder.bind(_server(_blender_dispatcher=dispatcher)) is True
    dispatcher.complete(result)
    _assert_unready(binder)


def test_success_callback_without_probe_execution_is_not_evidence():
    dispatcher = _AsyncDispatcher()
    binder = ReadinessBinder()
    assert binder.bind(_server(_blender_dispatcher=dispatcher)) is True
    dispatcher.complete({"success": True}, execute=False)
    _assert_unready(binder)


def test_rejected_async_submission_cannot_later_mark_ready():
    dispatcher = _AsyncDispatcher({"success": False, "status": "interrupted"})
    binder = ReadinessBinder()
    assert binder.bind(_server(_blender_dispatcher=dispatcher)) is False
    dispatcher.complete({"success": True})
    _assert_unready(binder)


def test_async_scheduling_exception_has_no_inline_fallback():
    class BrokenDispatcher:
        def submit_async_callable(self, **kwargs):
            raise RuntimeError("unavailable")

    binder = ReadinessBinder()
    assert binder.bind(_server(_blender_dispatcher=BrokenDispatcher())) is False
    _assert_unready(binder)


def test_custom_scheduler_exception_stays_unready():
    def scheduler(dispatcher, callback):
        raise RuntimeError("unavailable")

    binder = ReadinessBinder(probe_scheduler=scheduler)
    assert binder.bind(_server(_blender_dispatcher=object())) is False
    _assert_unready(binder)


def test_cancelled_queue_probe_never_marks_ready():
    queue = QueueDispatcher()
    binder = ReadinessBinder()
    assert binder.bind(_server(_blender_dispatcher=queue)) is True
    queue.shutdown()
    queue.tick(1)
    _assert_unready(binder)


def test_shutdown_queue_rejects_probe_scheduling():
    queue = QueueDispatcher()
    queue.shutdown()
    binder = ReadinessBinder()
    assert binder.bind(_server(_blender_dispatcher=queue)) is False
    _assert_unready(binder)


def _capture_scheduler(callbacks):
    def scheduler(dispatcher, callback):
        callbacks.append(callback)
        return True

    return scheduler


def test_revalidate_rejects_old_probe_and_resets_executor_readiness():
    callbacks = []
    binder = ReadinessBinder(probe_scheduler=_capture_scheduler(callbacks))
    binder.bind(_server(_blender_dispatcher=object()))
    callbacks[0]()
    assert binder.report()["main_thread_executor"] is True
    assert binder.revalidate_dispatcher() is True
    _assert_unready(binder)
    callbacks[0]()
    _assert_unready(binder)
    callbacks[1]()
    assert binder.report()["main_thread_executor"] is True


def test_rebind_rejects_previous_server_probe():
    callbacks = []
    binder = ReadinessBinder(probe_scheduler=_capture_scheduler(callbacks))
    binder.bind(_server(_blender_dispatcher=object()))
    binder.bind(_server(_blender_dispatcher=object()))
    callbacks[0]()
    _assert_unready(binder)
    callbacks[1]()
    assert binder.report()["dcc"] is True


def test_invalidate_rejects_late_success_and_revalidation():
    dispatcher = _AsyncDispatcher()
    binder = ReadinessBinder()
    binder.bind(_server(_blender_dispatcher=dispatcher))
    binder.invalidate()
    dispatcher.complete({"success": True})
    _assert_unready(binder)
    assert binder.report()["dispatcher"] is False
    assert binder.report()["host_execution_bridge"] is False
    assert binder.revalidate_dispatcher() is False
    binder.mark_dcc_ready(True)
    _assert_unready(binder)


def test_mark_dcc_unready_resets_main_thread_executor():
    queue = QueueDispatcher()
    binder = ReadinessBinder()
    binder.bind(_server(_blender_dispatcher=queue))
    queue.tick(1)
    assert binder.report()["main_thread_executor"] is True
    binder.mark_dcc_ready(False)
    _assert_unready(binder)
