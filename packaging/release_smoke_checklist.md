# Release Smoke Checklist — dcc-mcp-blender

Run these checks against every release ZIP before publishing.
This checklist validates the GUI Extension install path for Blender 4.2+.

## Prerequisites

- Blender 4.2.0 or later (LTS recommended)
- A clean Blender profile (no prior dcc-mcp-blender installed):
  ```bash
  blender --factory-startup
  ```
  Or delete/rename `%APPDATA%\Blender Foundation\Blender\<version>\extensions\`
- The release ZIP built by:
  ```bash
  python packaging/assemble_zip.py --platform win64 --output-dir dist_addon/
  ```

## 1. Extension Install from Disk

- [ ] Open Blender with a clean profile
- [ ] **Edit → Preferences → Extensions → Install from Disk…**
- [ ] Select the release ZIP (`dcc_mcp_blender_addon_<platform>_vX.Y.Z.zip`)
- [ ] Confirm the extension **"DCC MCP Blender"** appears in the Extensions list
- [ ] **DO NOT** use **Edit → Preferences → Add-ons → Install** — the legacy
  add-on path is unsupported. Installing there will produce:
  > *"ZIP packaged incorrectly; `__init__.py` should be in a directory, not at top-level"*
  This is expected — the ZIP uses the Blender 4.2+ Extension flat-package layout.

## 2. Server Auto-Start

- [ ] Enable the **DCC MCP Blender** extension
- [ ] Check Blender console / Info area:
  ```
  [DCC MCP Blender] Server started — http://127.0.0.1:8765/mcp
  ```
- [ ] Navigate to `http://127.0.0.1:8765/mcp` in a browser —
  expect `{"jsonrpc":"2.0","error":...}` (valid MCP endpoint, not a connection error)
- [ ] Navigate to `http://127.0.0.1:8765/health` — expect HTTP 200
- [ ] Navigate to `http://127.0.0.1:8765/docs` — expect OpenAPI docs page

## 3. MCP Initialize Handshake

- [ ] Send an MCP `initialize` request and verify server info:
  ```python
  import urllib.request, json
  body = json.dumps({
      "jsonrpc": "2.0",
      "id": 0,
      "method": "initialize",
      "params": {
          "protocolVersion": "2025-03-26",
          "capabilities": {},
          "clientInfo": {"name": "smoke", "version": "1"}
      }
  }).encode()
  req = urllib.request.Request(
      "http://127.0.0.1:8765/mcp", data=body,
      headers={"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"},
      method="POST"
  )
  resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
  assert resp["result"]["serverInfo"]["name"] == "dcc-mcp-blender"
  print("PASS: MCP initialize handshake")
  ```

## 4. tools/list — No Regression

- [ ] Verify `tools/list` returns 50+ tools:
  ```python
  body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}).encode()
  req = urllib.request.Request(
      "http://127.0.0.1:8765/mcp", data=body,
      headers={"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"},
      method="POST"
  )
  resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
  count = len(resp["result"]["tools"])
  assert count > 50, f"Expected >50 tools, got {count}"
  print(f"PASS: tools/list returned {count} tools")
  ```

## 5. Main-Thread Tool Execution (GUI Smoke)

These tools declare `thread_affinity: main` and call `bpy` APIs — they must NOT
fail with `THREAD_AFFINITY_UNAVAILABLE`.

- [ ] Call `get_scene_info` (read-only, main-thread affinity):
  ```python
  body = json.dumps({
      "jsonrpc": "2.0", "id": 2, "method": "tools/call",
      "params": {"name": "get_scene_info", "arguments": {}}
  }).encode()
  req = urllib.request.Request(
      "http://127.0.0.1:8765/mcp", data=body,
      headers={"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"},
      method="POST"
  )
  resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
  content = resp["result"]["content"]
  assert len(content) > 0
  assert "THREAD_AFFINITY_UNAVAILABLE" not in json.dumps(resp)
  print("PASS: get_scene_info executed on main thread")
  ```

- [ ] Call `create_object` (main-thread affinity, writes to `bpy.data`):
  ```python
  body = json.dumps({
      "jsonrpc": "2.0", "id": 3, "method": "tools/call",
      "params": {"name": "create_object",
                 "arguments": {"object_type": "cube", "name": "SmokeCube"}}
  }).encode()
  req = urllib.request.Request(
      "http://127.0.0.1:8765/mcp", data=body,
      headers={"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"},
      method="POST"
  )
  resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
  assert "THREAD_AFFINITY_UNAVAILABLE" not in json.dumps(resp)
  print("PASS: create_object executed on main thread")
  ```

- [ ] Verify the object actually appeared in Blender:
  ```python
  import bpy
  assert "SmokeCube" in bpy.data.objects
  print("PASS: SmokeCube exists in Blender scene")
  ```

## 6. Readiness Probe — /v1/readyz

- [ ] Check `/v1/readyz` returns all-green:
  ```python
  req = urllib.request.Request("http://127.0.0.1:8765/v1/readyz")
  resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
  print(json.dumps(resp, indent=2))
  assert resp.get("process") is True, "process bit should be True"
  assert resp.get("dispatcher") is True, "dispatcher bit should be True"
  assert resp.get("dcc") is True, "dcc bit should be True"
  print("PASS: readiness probe all-green")
  ```

- [ ] Verify `main_thread_executor` is also True (deferred by the dcc probe):
  ```python
  # Check the readiness report from the server's own API
  assert resp.get("main_thread_executor") is True, \
      "main_thread_executor should be True after pump verification"
  ```

## 7. Graceful Shutdown & Restart

- [ ] Disable the **DCC MCP Blender** extension in Preferences → Extensions
- [ ] Confirm server port is released (no HTTP response on `http://127.0.0.1:8765`)
- [ ] Re-enable the extension and verify server restarts cleanly
- [ ] Verify `/v1/readyz` goes through the green transition again

## 8. Gateway Multi-Instance (Optional)

If two Blender instances are available:

- [ ] Start Blender #1 with the extension enabled — verify it becomes gateway
- [ ] Start Blender #2 with the extension enabled —
  verify it registers on an ephemeral port
- [ ] Check `http://127.0.0.1:8765/gateway/instances` — both should appear
- [ ] Close Blender #1 — verify Blender #2 takes over gateway port

---

## Quick Smoke Script

Save as `smoke_test.py` and run against a running Blender instance:

```python
"""Quick MCP smoke test — requires requests: pip install requests"""
import json, sys, requests

BASE = "http://127.0.0.1:8765"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

def mcp(method, params=None, request_id=None):
    body = {"jsonrpc": "2.0", "id": request_id or 0, "method": method}
    if params is not None:
        body["params"] = params
    r = requests.post(f"{BASE}/mcp", json=body, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def check(name, ok):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    if not ok:
        sys.exit(1)

# 1. Initialize
init = mcp("initialize", {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {"name": "smoke", "version": "1"},
})
check("initialize", init["result"]["serverInfo"]["name"] == "dcc-mcp-blender")

# 2. tools/list
tools = mcp("tools/list", {})
count = len(tools["result"]["tools"])
check(f"tools/list ({count} tools)", count > 50)

# 3. Main-thread get_scene_info
scene = mcp("tools/call", {"name": "get_scene_info", "arguments": {}}, request_id=2)
check("get_scene_info (main-thread)", "THREAD_AFFINITY_UNAVAILABLE" not in json.dumps(scene))

# 4. Main-thread create_object
create = mcp("tools/call", {
    "name": "create_object",
    "arguments": {"object_type": "cube", "name": "SmokeCube"}
}, request_id=3)
check("create_object (main-thread)", "THREAD_AFFINITY_UNAVAILABLE" not in json.dumps(create))

# 5. Readiness
r = requests.get(f"{BASE}/v1/readyz", timeout=5)
ready = r.json()
check("readyz process", ready.get("process") is True)
check("readyz dispatcher", ready.get("dispatcher") is True)
check("readyz dcc", ready.get("dcc") is True)

print("\n🎉 All smoke tests passed!")
```
