"""Runtime readiness wiring for :class:`BlenderMcpServer`.

Delegates probe lifecycle to core :class:`dcc_mcp_core.readiness.AdapterReadinessBinder`
(0.17.32+) while retaining the Blender-specific dispatcher-probe pattern via
:func:`_default_probe_scheduler`.

The probe itself (``process`` / ``dispatcher`` / ``dcc`` bits) lives in
``dcc-mcp-core`` as :class:`dcc_mcp_core.ReadinessProbe`; this module only
owns the *wiring*:

* ``process``    — flipped by core the moment the server object exists.
* ``dispatcher`` — flipped as soon as the binder runs (the execution bridge
  is wired during ``__init__``). ``main_thread_executor`` is deferred
  until the dcc probe verifies the main-thread pump is functional.
* ``dcc``        — flipped only after a callback runs on the attached host
  dispatcher's pump, including background mode.

Scheduling never installs a Blender timer or runs a fallback inline. Missing
or failed dispatch routes remain unready, and callbacks from an older binding
cannot revive a stopped or revalidated server.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from typing import Any, Callable, Optional

from dcc_mcp_core.readiness import AdapterReadinessBinder

from . import _env

logger = logging.getLogger(__name__)

ENV_READINESS_TIMEOUT_SECS = _env.ENV_READINESS_TIMEOUT_SECS
READINESS_PROBE_REQUEST_ID = "dcc_mcp_blender__readiness__dcc_ready_probe"

ProbeScheduler = Callable[[Any, Callable[[], None]], bool]


def resolve_readiness_timeout_secs(readiness_timeout_secs: Optional[int] = None) -> Optional[int]:
    """Resolve :data:`ENV_READINESS_TIMEOUT_SECS` into a positive integer or ``None``."""
    return _env.resolve_readiness_timeout_secs(readiness_timeout_secs)


def _default_probe_scheduler(dispatcher: Any, on_done: Callable[[], None]) -> bool:
    """Queue a probe without touching Blender's native timer API."""
    host_dispatcher = getattr(dispatcher, "host_dispatcher", None)
    queue = host_dispatcher if host_dispatcher is not None else dispatcher
    post = getattr(queue, "post", None)
    if callable(post) and callable(getattr(queue, "tick", None)):
        try:
            is_shutdown = getattr(queue, "is_shutdown", False)
            if is_shutdown() if callable(is_shutdown) else is_shutdown:
                return False
            post(on_done)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] readiness: queue post failed: %s", exc)
            return False

    submit_async = getattr(dispatcher, "submit_async_callable", None)
    if callable(submit_async):
        state_lock = threading.Lock()
        executed = completed = accepted = False

        def _task() -> None:
            nonlocal executed
            with state_lock:
                executed = True

        def _on_complete(result: Any) -> None:
            nonlocal completed
            with state_lock:
                completed = executed and _successful_outcome(result)
                notify = accepted and completed
            if notify:
                on_done()

        try:
            result = submit_async(
                request_id=READINESS_PROBE_REQUEST_ID,
                task=_task,
                affinity="main",
                timeout_ms=5_000,
                on_complete=_on_complete,
            )
            with state_lock:
                accepted = _successful_outcome(result)
                notify = accepted and completed
            if notify:
                on_done()
            return accepted
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] readiness: submit_async_callable failed: %s", exc)
    return False


def _successful_outcome(result: Any) -> bool:
    """Require Core's explicit success envelope, excluding terminal failures."""
    return (
        isinstance(result, Mapping)
        and result.get("success") is True
        and result.get("status") not in {"failed", "interrupted", "cancelled", "canceled", "expired", "timeout"}
    )


def _probe_dispatcher(server: Any) -> Any:
    """Verify the bridge's HTTP queue, falling back to its retained pump owner."""
    bridge = getattr(server, "_execution_bridge", None)
    if bridge is not None:
        try:
            resolver = getattr(bridge, "resolve_host_dispatcher", None)
            dispatcher = resolver() if callable(resolver) else getattr(bridge, "host_dispatcher", None)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] readiness: host dispatcher resolution failed: %s", exc)
            return None
        if dispatcher is not None:
            return dispatcher
    dispatcher = getattr(server, "_pump_dispatcher", None)
    if dispatcher is not None:
        return dispatcher
    return getattr(server, "_blender_dispatcher", None)


class ReadinessBinder:
    """Drive readiness using core :class:`AdapterReadinessBinder` with Blender lifecycle hooks."""

    def __init__(
        self,
        *,
        timeout_secs: Optional[int] = None,
        probe_scheduler: Optional[ProbeScheduler] = None,
    ) -> None:
        from dcc_mcp_core import ReadinessProbe  # noqa: PLC0415

        self.timeout_secs: Optional[int] = resolve_readiness_timeout_secs(timeout_secs)
        self.probe: ReadinessProbe = ReadinessProbe()
        self.probe_scheduler: ProbeScheduler = probe_scheduler or _default_probe_scheduler
        self._adapter_binder: Optional[AdapterReadinessBinder] = None
        self.bound_server: Any = None
        self.bound_dispatcher: Any = None
        self.dcc_scheduled: bool = False
        self._lock = threading.RLock()
        self._generation = 0
        self._active = False

    @property
    def published_to_server(self) -> bool:
        """Whether the probe was published to the inner Rust server."""
        return self._adapter_binder.published if self._adapter_binder else False

    def report(self) -> dict:
        """Return the current three-state readiness snapshot."""
        return self.probe.report()

    def is_ready(self) -> bool:
        """Return ``True`` when all three bits are green."""
        return self.probe.is_ready()

    def bind(self, server: Any) -> bool:
        """Wire the probe into *server*."""
        with self._lock:
            if self.bound_server is server and self._active:
                return self.dcc_scheduled
            self._generation += 1
            self._active = True
            self.bound_server = server
            self._adapter_binder = AdapterReadinessBinder(server, probe=self.probe, publish=True)
            self.bound_dispatcher = _probe_dispatcher(server)
            present = self.bound_dispatcher is not None
            self._adapter_binder.mark_dispatcher_ready(
                present,
                host_execution_bridge_ready=present,
                main_thread_executor_ready=False,
                dcc_ready=False,
            )
        return self._schedule_probe()

    def _schedule_probe(self) -> bool:
        with self._lock:
            generation = self._generation
            dispatcher = self.bound_dispatcher
            self.dcc_scheduled = False
            if not self._active or dispatcher is None:
                return False

        def _on_done() -> None:
            with self._lock:
                if self._active and generation == self._generation:
                    self.mark_dcc_ready()

        try:
            scheduled = bool(self.probe_scheduler(dispatcher, _on_done))
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] readiness: probe scheduler raised: %s", exc)
            scheduled = False
        with self._lock:
            if not self._active or generation != self._generation:
                return False
            self.dcc_scheduled = scheduled
            if not scheduled:
                self.mark_dcc_ready(False)
            return scheduled

    def mark_dispatcher_ready(self, value: bool = True) -> None:
        """Flip the ``dispatcher`` bit."""
        try:
            self.probe.set_dispatcher_ready(value)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] readiness: set_dispatcher_ready failed: %s", exc)

    def mark_dcc_ready(self, value: bool = True) -> None:
        """Flip the ``dcc`` bit (and ``main_thread_executor`` once verified)."""
        with self._lock:
            if value and not self._active:
                return
            try:
                self.probe.set_dcc_ready(value)
                self.probe.set_main_thread_executor_ready(value)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[blender] readiness: set_dcc_ready failed: %s", exc)
                return
        if value:
            logger.info("[blender] readiness: dcc-ready — main thread is pumping")

    def revalidate_dispatcher(self) -> bool:
        """Re-probe the dispatcher after a scene reset that may have wiped timers.

        Resets the ``dcc`` readiness bit and schedules a new main-thread probe.
        Callers (e.g. ``new_scene``) should have already re-registered the timer
        pump before invoking this.

        Returns:
            ``True`` if a probe was scheduled, ``False`` if no dispatcher is bound.
        """
        with self._lock:
            self._generation += 1
            self.mark_dcc_ready(False)
            if not self._active:
                self.dcc_scheduled = False
                return False
            self.bound_dispatcher = _probe_dispatcher(self.bound_server)
        return self._schedule_probe()

    def invalidate(self) -> None:
        """Reject pending probe callbacks when the owning server stops."""
        with self._lock:
            self._generation += 1
            self._active = False
            self.dcc_scheduled = False
            self.mark_dcc_ready(False)
            if self._adapter_binder is not None:
                self._adapter_binder.mark_dispatcher_ready(False, host_execution_bridge_ready=False)


def install_readiness(
    server: Any,
    *,
    timeout_secs: Optional[int] = None,
    probe_scheduler: Optional[ProbeScheduler] = None,
) -> Optional[ReadinessBinder]:
    """One-shot helper used by :class:`BlenderMcpServer.__init__`.

    Returns the bound :class:`ReadinessBinder`, or ``None`` when the core
    ``ReadinessProbe`` API is unavailable (older core) so startup never
    raises on an optional integration.
    """
    try:
        binder = ReadinessBinder(timeout_secs=timeout_secs, probe_scheduler=probe_scheduler)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[blender] readiness unavailable: %s", exc)
        return None
    binder.bind(server)
    return binder
