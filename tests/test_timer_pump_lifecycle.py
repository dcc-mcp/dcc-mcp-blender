"""Owner-thread and retained-callback contracts for Blender's native pump."""

from __future__ import annotations

import sys
import threading
from types import SimpleNamespace
from typing import Callable

import pytest

from dcc_mcp_blender.host import BlenderTimerPump, BlenderUiDispatcher


class _Timers:
    def __init__(self) -> None:
        self.registered: list[Callable] = []
        self.calls: list[tuple[str, int]] = []
        self.fail_register = False
        self.fail_unregister = False

    def register(self, callback, **kwargs) -> None:
        self.calls.append(("register", threading.get_ident()))
        assert kwargs == {"first_interval": 0.0, "persistent": True}
        self.registered.append(callback)
        if self.fail_register:
            raise RuntimeError("native register failed")

    def is_registered(self, callback) -> bool:
        self.calls.append(("is_registered", threading.get_ident()))
        return callback in self.registered

    def unregister(self, callback) -> None:
        self.calls.append(("unregister", threading.get_ident()))
        if self.fail_unregister:
            raise RuntimeError("native unregister failed")
        self.registered.remove(callback)


@pytest.fixture
def timers(monkeypatch):
    timers = _Timers()
    monkeypatch.setitem(sys.modules, "bpy", SimpleNamespace(app=SimpleNamespace(timers=timers)))
    return timers


def _worker_call(callback):
    results = []
    errors = []

    def run():
        try:
            results.append(callback())
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    return worker, results, errors


def _join(worker):
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_prestart_worker_submission_waits_for_owner_timer(timers):
    owner_ident = threading.get_ident()
    dispatcher = BlenderUiDispatcher()
    invoked_on = []
    worker, results, errors = _worker_call(
        lambda: dispatcher.submit_async_callable("probe", lambda: invoked_on.append(threading.get_ident()))
    )
    _join(worker)

    assert errors == []
    assert results[0]["success"] is True
    assert dispatcher.pending_count() == 1
    assert timers.calls == []
    assert invoked_on == []

    dispatcher.start()
    dispatcher.start()
    assert len(timers.registered) == 1
    timers.registered[0]()
    assert invoked_on == [owner_ident]
    assert all(thread_ident == owner_ident for _call, thread_ident in timers.calls)
    dispatcher.stop()


def test_worker_synchronous_dispatch_never_calls_bpy(timers):
    owner_ident = threading.get_ident()
    queued = threading.Event()
    dispatcher = BlenderUiDispatcher(timeout_ms=1000)
    dispatcher.on_job_queued = lambda _job: queued.set()
    dispatcher.start()
    calls_before_submit = list(timers.calls)
    worker, results, errors = _worker_call(lambda: dispatcher.dispatch_callable(threading.get_ident))
    assert queued.wait(timeout=1)
    assert timers.calls == calls_before_submit

    timers.registered[0]()
    _join(worker)
    assert errors == []
    assert results == [owner_ident]
    dispatcher.stop()
    assert all(thread_ident == owner_ident for _call, thread_ident in timers.calls)


@pytest.mark.parametrize("operation", ["install", "uninstall", "verify_installed"])
def test_native_timer_management_refuses_workers_before_bpy(timers, operation):
    pump = BlenderTimerPump()
    pump.install(lambda: 0.5)
    calls_before = list(timers.calls)
    callback = (lambda: pump.install(lambda: 0.5)) if operation == "install" else getattr(pump, operation)
    worker, _results, errors = _worker_call(callback)
    _join(worker)

    assert len(errors) == 1
    assert "owner thread" in str(errors[0])
    assert timers.calls == calls_before
    assert pump.is_installed
    pump.uninstall()


@pytest.mark.parametrize("use_timer", [False, True])
def test_worker_cannot_drain_blender_jobs(timers, use_timer):
    dispatcher = BlenderUiDispatcher()
    invoked = []
    dispatcher.start()
    dispatcher.submit_async_callable("queued", lambda: invoked.append(True))
    callback = timers.registered[0] if use_timer else lambda: dispatcher.drain_queue(200.0)
    worker, _results, errors = _worker_call(callback)
    _join(worker)

    assert len(errors) == 1
    assert "owner thread" in str(errors[0])
    assert invoked == []
    assert dispatcher.pending_count() == 1
    timers.registered[0]()
    assert invoked == [True]
    dispatcher.stop()


def test_cancel_before_tick_does_not_execute(timers):
    dispatcher = BlenderUiDispatcher()
    invoked = []
    dispatcher.start()
    dispatcher.submit_async_callable("cancelled", lambda: invoked.append(True))
    assert dispatcher.cancel("cancelled")

    timers.registered[0]()
    assert invoked == []
    assert dispatcher.pending_count() == 0
    dispatcher.stop()


def test_adapter_timeout_before_tick_cancels_core_request(timers):
    dispatcher = BlenderUiDispatcher(timeout_ms=10)
    invoked = []
    dispatcher.start()
    worker, _results, errors = _worker_call(lambda: dispatcher.dispatch_callable(lambda: invoked.append(True)))
    _join(worker)
    assert len(errors) == 1
    assert "Timeout" in str(errors[0])

    timers.registered[0]()
    assert invoked == []
    assert dispatcher.pending_count() == 0
    dispatcher.stop()


def test_timeout_after_core_dequeue_refuses_late_callable_admission(timers):
    dispatcher = BlenderUiDispatcher(timeout_ms=1000)
    invoked = []
    queued = threading.Event()
    dequeued = threading.Event()
    caller_failed = threading.Event()

    class _TimeoutWhenDequeued(threading.Event):
        def wait(self, timeout=None):
            assert dequeued.wait(timeout=1)
            return False

    def on_queued(job):
        job.event = _TimeoutWhenDequeued()
        queued.set()

    def on_started(_job):
        # Core has marked the job active, but has not called our closure yet.
        dequeued.set()
        assert caller_failed.wait(timeout=1)

    def dispatch():
        try:
            return dispatcher.dispatch_callable(lambda: invoked.append(True))
        finally:
            caller_failed.set()

    dispatcher.on_job_queued = on_queued
    dispatcher.on_job_started = on_started
    dispatcher.start()
    worker, _results, errors = _worker_call(dispatch)
    assert queued.wait(timeout=1)

    timers.registered[0]()
    _join(worker)
    assert len(errors) == 1
    assert "Timeout" in str(errors[0])
    assert invoked == []
    assert dispatcher.pending_count() == 0
    assert dispatcher.active_count() == 0
    dispatcher.stop()


def test_timeout_after_callable_admission_preserves_running_work(timers, monkeypatch):
    dispatcher = BlenderUiDispatcher(timeout_ms=1000)
    invoked = []
    queued = threading.Event()
    invocation_started = threading.Event()
    caller_failed = threading.Event()
    cancel_calls = []
    monkeypatch.setattr(dispatcher, "cancel", lambda request_id: cancel_calls.append(request_id))

    class _TimeoutWhenStarted(threading.Event):
        def wait(self, timeout=None):
            assert invocation_started.wait(timeout=1)
            return False

    def on_queued(job):
        job.event = _TimeoutWhenStarted()
        queued.set()

    def task():
        invocation_started.set()
        assert caller_failed.wait(timeout=1)
        invoked.append("completed")

    def dispatch():
        try:
            return dispatcher.dispatch_callable(task)
        finally:
            caller_failed.set()

    dispatcher.on_job_queued = on_queued
    dispatcher.start()
    worker, _results, errors = _worker_call(dispatch)
    assert queued.wait(timeout=1)

    timers.registered[0]()
    _join(worker)
    assert len(errors) == 1
    assert "Timeout" in str(errors[0])
    assert invoked == ["completed"]
    assert cancel_calls == []
    dispatcher.stop()


@pytest.mark.parametrize("affinity", ["main", "any"])
def test_shutdown_rejects_later_owner_and_worker_dispatch(timers, affinity):
    dispatcher = BlenderUiDispatcher()
    invoked = []
    dispatcher.start()
    stale_tick = timers.registered[0]
    dispatcher.stop()

    with pytest.raises(RuntimeError, match="shut down"):
        dispatcher.dispatch_callable(lambda: invoked.append(True), affinity=affinity)
    worker, _results, errors = _worker_call(
        lambda: dispatcher.dispatch_callable(lambda: invoked.append(True), affinity=affinity)
    )
    _join(worker)
    assert len(errors) == 1
    assert "shut down" in str(errors[0])
    assert stale_tick() is None
    assert invoked == []
    with pytest.raises(RuntimeError, match="shut down"):
        dispatcher.start()


def test_old_callback_cannot_drain_new_generation(timers):
    dispatcher = BlenderUiDispatcher()
    invoked = []
    dispatcher.start()
    old_tick = timers.registered[0]
    dispatcher.stop_pump()
    dispatcher.start_pump()
    new_tick = timers.registered[0]
    dispatcher.submit_async_callable("new-generation", lambda: invoked.append(True))

    assert old_tick() is None
    assert invoked == []
    assert dispatcher.pump.pump_count() == 0
    new_tick()
    assert invoked == [True]
    dispatcher.stop()


def test_failed_registration_fences_retained_callback_and_allows_retry(timers):
    pump = BlenderTimerPump()
    invoked = []
    timers.fail_register = True
    with pytest.raises(RuntimeError, match="native register failed"):
        pump.install(lambda: invoked.append("old"))
    old_tick = timers.registered[0]
    assert not pump.is_installed
    assert old_tick() is None

    timers.fail_register = False
    pump.install(lambda: invoked.append("new"))
    assert old_tick() is None
    timers.registered[-1]()
    assert invoked == ["new"]
    pump.uninstall()


def test_failed_unregister_fences_retained_callback(timers):
    pump = BlenderTimerPump()
    invoked = []
    pump.install(lambda: invoked.append("old"))
    old_tick = timers.registered[0]
    timers.fail_unregister = True
    with pytest.raises(RuntimeError, match="native unregister failed"):
        pump.uninstall()
    assert not pump.is_installed
    assert old_tick() is None

    timers.fail_unregister = False
    pump.install(lambda: invoked.append("new"))
    assert old_tick() is None
    timers.registered[-1]()
    assert invoked == ["new"]
    pump.uninstall()


def test_missing_native_timer_invalidates_generation(timers):
    pump = BlenderTimerPump()
    invoked = []
    pump.install(lambda: invoked.append("old"))
    old_tick = timers.registered[0]
    timers.registered.clear()
    assert not pump.verify_installed()
    assert not pump.is_installed
    pump.install(lambda: invoked.append("new"))

    assert old_tick() is None
    timers.registered[0]()
    assert invoked == ["new"]
    pump.uninstall()
