# MCP protocol compatibility

`dcc-mcp-blender` delegates MCP HTTP negotiation to `dcc-mcp-core`. The
adapter's released dependency range is `dcc-mcp-core>=0.20.0,<1.0.0`; the
adapter must not copy Core's negotiation logic or require a development wheel.

## Compatibility matrix

| Client request | Wire mode | Adapter status | Negotiated version | Contract test |
| --- | --- | --- | --- | --- |
| `2025-03-26` | Session (`initialize`) | Supported for legacy clients | `2025-03-26` | `test_initialize_protocol_matrix` |
| `2025-06-18` | Session (`initialize`) | Supported and preferred | `2025-06-18` | `test_initialize_protocol_matrix` |
| `2026-07-28` | Stateless (`server/discover`) | Not claimed by this release | `2025-06-18` fallback | `test_initialize_protocol_matrix` |
| Unknown or omitted | Session (`initialize`) | Supported via Core fallback | `2025-06-18` | `test_initialize_protocol_matrix` |

The 2026 row is intentionally explicit: current dcc-mcp-core `main` contains
an opt-in stateless implementation, but this adapter release is built and
tested against released Core wheels with the session default. A future
adapter release can claim stateless support only after a released Core wheel,
an add-on packaging smoke, and a live Blender HTTP check cover that path.

## HTTP boundary

- Endpoint: `POST /mcp` (the URL is returned by `BlenderMcpServer.mcp_url`).
- Requests use JSON-RPC 2.0 with `Content-Type: application/json`.
- Clients may advertise `Accept: application/json, text/event-stream`.
- Core owns transport envelopes, session state, and version negotiation.
- Blender owns `serverInfo.name` (`dcc-mcp-blender`) and the adapter version.

Run the adapter-facing contract checks with:

```text
python -m pytest tests/test_protocol_compatibility.py
```

The checks use an OS-assigned loopback port and only the released dependency
range, so they do not require a Core `main` checkout or unreleased wheel.

