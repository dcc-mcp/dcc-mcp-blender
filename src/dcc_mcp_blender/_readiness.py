"""Runtime readiness wiring for :class:`BlenderMcpServer`.

Delegates probe lifecycle to core :class:`dcc_mcp_core.readiness.AdapterReadinessBinder`
(0.17.32+) while retaining the Blender-specific dispatcher-probe pattern via
:func:`_default_probe_scheduler`.

The probe itself (``process`` / ``dispatcher`` / ``dcc`` bits) lives in
``dcc-mcp-core`` as :class:`dcc_mcp_core.ReadinessProbe`; this module only
owns the *wiring*:

* ``process``    — flipped by core the moment the server object exists.
* ``dispatcher`` — flipped as soon as the binder runs (the execution bridge
  is wired during ``__init__``).
* ``dcc``        — flipped after a no-op is marshalled onto Blender's main
  thread (via the attached host dispatcher / ``bpy.app.timers`` pump), or
  immediately in background (``--background``) / standalone mode where the
  HTTP worker thread *is* the pump.

Every step degrades gracefully: a missing ``ReadinessProbe`` API or a
dispatcher without async submission still produces a usable binder.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from dcc_mcp_core.readiness import AdapterReadinessBinder

from dcc_mcp_blender import _env

logger = logging.getLogger(__name__)

ENV_READINESS_TIMEOUT_SECS = _env.ENV_READINESS_TIMEOUT_SECS
READINESS_PROBE_REQUEST_ID = "dcc_mcp_blender__readiness__dcc_ready_probe"

ProbeScheduler = Callable[[Any, Callable[[], None]], bool]


def resolve_readiness_timeout_secs(readiness_timeout_secs: Optional[int] = None) -> Optional[int]:
    """Resolve :data:`ENV_READINESS_TIMEOUT_SECS` into a positive integer or ``None``."""
    return _env.resolve_readiness_timeout_secs(readiness_timeout_secs)


def _default_probe_scheduler(dispatcher: Any, on_done: Callable[[], None]) -> bool:
    """Schedule a dcc-ready probe on *dispatcher*.

    Prefers ``submit_async_callable`` (core UI dispatchers) so the no-op
    runs on Blender's main thread; falls back to an immediate ``on_done()``
    when no async path exists (post/tick-style dispatchers).
    """
    submit_async = getattr(dispatcher, "submit_async_callable", None)
    if callable(submit_async):

        def _on_complete(_result: Any) -> None:
            on_done()

        try:
            submit_async(
                request_id=READINESS_PROBE_REQUEST_ID,
                task=lambda: None,
                affinity="main",
                timeout_ms=5_000,
                on_complete=_on_complete,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] readiness: submit_async_callable failed: %s", exc)

    # No async path available — flip the bit immediately so a usable
    # dispatcher never leaves ``dcc`` permanently red.
    on_done()
    return True


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
        if self.bound_server is server:
            return self.dcc_scheduled
        self.bound_server = server

        self._adapter_binder = AdapterReadinessBinder(server, probe=self.probe, publish=True)
        self._adapter_binder.mark_dispatcher_ready(
            True,
            host_execution_bridge_ready=True,
            main_thread_executor_ready=True,
        )

        dispatcher = getattr(server, "_blender_dispatcher", None)
        if dispatcher is None:
            self.bound_dispatcher = None
            self._adapter_binder.mark_inline_ready()
            self.dcc_scheduled = True
            return True

        self.bound_dispatcher = dispatcher
        try:
            self.dcc_scheduled = bool(self.probe_scheduler(dispatcher, self.mark_dcc_ready))
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] readiness: probe scheduler raised: %s", exc)
            self.mark_dcc_ready()
            self.dcc_scheduled = True
        return self.dcc_scheduled

    def mark_dispatcher_ready(self, value: bool = True) -> None:
        """Flip the ``dispatcher`` bit."""
        try:
            self.probe.set_dispatcher_ready(value)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] readiness: set_dispatcher_ready failed: %s", exc)

    def mark_dcc_ready(self, value: bool = True) -> None:
        """Flip the ``dcc`` bit."""
        try:
            self.probe.set_dcc_ready(value)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] readiness: set_dcc_ready failed: %s", exc)
            return
        if value:
            logger.info("[blender] readiness: dcc-ready — main thread is pumping")


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
