# dcc-mcp-blender

> Blender addon for the [DCC Model Context Protocol (MCP)](https://github.com/loonghao/dcc-mcp-core) ecosystem — embeds a Streamable HTTP MCP server directly inside Blender, letting any MCP-compatible AI client drive your 3D workflow.

[![PyPI version](https://badge.fury.io/py/dcc-mcp-blender.svg)](https://badge.fury.io/py/dcc-mcp-blender)
[![CI](https://github.com/loonghao/dcc-mcp-blender/actions/workflows/ci.yml/badge.svg)](https://github.com/loonghao/dcc-mcp-blender/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## Overview

`dcc-mcp-blender` turns Blender into a first-class MCP server. Once the addon is enabled, any MCP client (Claude Desktop, custom agents, etc.) can call Blender tools over HTTP without any external gateway.

```
┌─────────────────────────────────┐
│  Blender (Python 3.10+)         │
├─────────────────────────────────┤
│  dcc_mcp_blender                │
│  ├─ BlenderMcpServer            │
│  ├─ SkillCatalog (50+ skills)   │
│  ├─ ActionRegistry              │
│  └─ HTTP Handlers               │
├─────────────────────────────────┤
│  dcc-mcp-core                   │
│  ├─ McpHttpServer               │
│  ├─ JSON-RPC 2.0                │
│  └─ SSE Streaming               │
└─────────────────────────────────┘
         ↓ http://127.0.0.1:8765/mcp
┌─────────────────────────────────┐
│  MCP Host (Claude / etc.)       │
└─────────────────────────────────┘
```

---

## Features

- **Embedded MCP server** — no external gateway needed; the server runs inside Blender's Python interpreter
- **50+ pre-built skills** — scene management, object manipulation, materials, rendering, scripting and more
- **Extensible skill system** — drop new skill folders alongside built-ins or point to them via env vars
- **Main-thread host adapter** — `BlenderHost` drives dispatcher ticks through `bpy.app.timers` or a background loop
- **Streamable HTTP transport** — compatible with any MCP 2025-03-26 client
- **Claude Desktop ready** — ship a one-line `mcpServers` config and you're done

---

## Available MCP Tools

| Category | Tools |
|---|---|
| **blender-scene** | `new_scene`, `open_scene`, `save_scene`, `list_objects`, `get_scene_info`, `get_session_info` |
| **blender-objects** | `create_object`, `delete_object`, `duplicate_object`, `move_object`, `rotate_object`, `scale_object`, `list_objects` |
| **blender-mesh** | `create_mesh`, `apply_modifier`, `subdivide_mesh`, `extrude_faces`, `merge_vertices` |
| **blender-materials** | `create_material`, `assign_material`, `set_material_color`, `list_materials`, `delete_material` |
| **blender-render** | `render_scene`, `set_render_settings`, `set_camera`, `get_render_info` |
| **blender-scripting** | `execute_python`, `execute_script_file`, `get_blender_info` |
| **blender-animation** | `set_keyframe`, `delete_keyframe`, `set_frame_range`, `get_frame_range`, `bake_action` |
| **blender-lighting** | `create_light`, `delete_light`, `set_light_properties`, `list_lights` |
| **blender-camera** | `create_camera`, `set_active_camera`, `set_camera_properties`, `list_cameras` |
| **blender-collection** | `create_collection`, `link_to_collection`, `unlink_from_collection`, `list_collections` |
| **blender-geometry** | `create_sphere`, `save_blend`, `file_exists`, `export_fbx`, `export_obj` |

---

## Installation

### Option 1 — Install as Blender Addon (ZIP)

1. Download the latest platform ZIP from the [Releases](https://github.com/loonghao/dcc-mcp-blender/releases) page:
   `dcc_mcp_blender_addon_win64_vX.Y.Z.zip`, `dcc_mcp_blender_addon_linux_vX.Y.Z.zip`, or
   `dcc_mcp_blender_addon_macos_vX.Y.Z.zip`
2. In Blender 4.2+: **Edit → Preferences → Extensions → Install from Disk…** → select the ZIP
3. Enable **DCC MCP Blender**
4. The MCP server starts automatically on `http://127.0.0.1:8765`

Release ZIPs include `blender_manifest.toml` and the matching `dcc-mcp-core` wheel under `wheels/`, so Blender installs the Python dependency into the extension's isolated environment.

The addon ZIP is assembled by `packaging/assemble_zip.py`. It resolves the latest compatible `dcc-mcp-core` wheel, places it under `wheels/`, and injects that wheel into `blender_manifest.toml`; Blender 4.2+ then installs it through the extension wheel mechanism instead of relying on global `pip` packages or `sys.path` edits.

### Option 2 — Install via pip (for scripts / CI)

```bash
pip install dcc-mcp-blender
```

Then in Blender's Python console:

```python
import dcc_mcp_blender
dcc_mcp_blender.start_server()
```

### Headless Bootstrap

For CI or automation that needs Blender's main thread dispatcher:

```bash
blender --background --python src/dcc_mcp_blender/blender_bootstrap.py
```

The bootstrap prints `MCP_URL=...`, discovers bundled skills, and drives `BlenderHost` in headless mode until the process is stopped.

---

## Quick Start

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "blender": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Make sure the Blender addon is enabled and the server is running, then restart Claude Desktop.

### Python API

```python
import dcc_mcp_blender

# Start the server (default port 8765)
dcc_mcp_blender.start_server()

# Stop the server
dcc_mcp_blender.stop_server()
```

---

## Development

```bash
git clone https://github.com/loonghao/dcc-mcp-blender
cd dcc-mcp-blender
pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
