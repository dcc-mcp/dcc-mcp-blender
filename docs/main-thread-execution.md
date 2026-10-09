# Blender main-thread execution

Create and start the server from Blender's main thread. Both the keyword and
`BlenderServerOptions` entry points create a default dispatcher when neither a
dispatcher nor an execution bridge is supplied. Construction rejects a failed
dispatcher or in-process executor binding before any skills are loaded.

```python
import dcc_mcp_blender

server = dcc_mcp_blender.start_server()
```

In GUI mode, the adapter starts Blender's persistent timer before publishing
the HTTP service. Workers enqueue through Core; they never install, unregister,
inspect or drain Blender timers. Explicit execution bridges take precedence
over other dispatcher arguments, and readiness probes use the bridge's actual
HTTP host queue.

Discovery proves that a service is registered. `dcc` and
`main_thread_executor` readiness require a callback to execute through the host
queue. Unsupported routes, submission failures, cancellations and callbacks
from an earlier binding cannot make readiness succeed.

Stopping invalidates readiness, shuts down queued work and detaches the timer
even if Core teardown fails. Timer callbacks retained across uninstall or
reinstall cannot drain a new generation. A stopped server cannot be restarted;
create a fresh server instead. A timed-out adapter call that has not entered its
callback cannot start later. Already running callbacks retain Core's cooperative
cancellation behavior.

If a GUI instance reports that no in-process executor is set, inspect its exact
installed and loaded package versions and startup entry point. Updating a wheel
on disk does not update an existing process or repair its singleton. Preserve
the failed call, then qualify a fresh, owned host against the frozen candidate.
Do not repair a running user's instance with a timer or executor monkeypatch.

Offline regression checks:

```text
python -m pytest tests/test_default_dispatcher_wiring.py tests/test_host_adapter.py tests/test_timer_pump_lifecycle.py tests/test_readiness_lifecycle.py tests/test_core_integrations.py
```

Real host acceptance additionally requires fresh process/package identity,
official skill registration, strict readiness, an actual main-thread readback,
unchanged scene/file evidence and graceful cleanup. Offline tests and background
CI do not establish GUI acceptance.
