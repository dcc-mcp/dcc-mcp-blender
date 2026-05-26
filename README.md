# dcc-mcp-blender

> Blender addon for the [DCC Model Context Protocol (MCP)](https://github.com/loonghao/dcc-mcp-core) ecosystem — embeds a Streamable HTTP MCP server directly inside Blender, letting any MCP-compatible AI client drive your 3D workflow.

[![PyPI version](https://badge.fury.io/py/dcc-mcp-blender.svg)](https://badge.fury.io/py/dcc-mcp-blender)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/dcc-mcp-blender.svg)](https://pypi.org/project/dcc-mcp-blender/)
[![PyPI - Wheel](https://img.shields.io/pypi/wheel/dcc-mcp-blender.svg)](https://pypi.org/project/dcc-mcp-blender/#files)
[![CI](https://github.com/loonghao/dcc-mcp-blender/actions/workflows/ci.yml/badge.svg)](https://github.com/loonghao/dcc-mcp-blender/actions/workflows/ci.yml)
[![E2E Blender](https://github.com/loonghao/dcc-mcp-blender/actions/workflows/e2e.yml/badge.svg)](https://github.com/loonghao/dcc-mcp-blender/actions/workflows/e2e.yml)
[![Release](https://github.com/loonghao/dcc-mcp-blender/actions/workflows/release.yml/badge.svg)](https://github.com/loonghao/dcc-mcp-blender/actions/workflows/release.yml)
[![PyPI Downloads](https://img.shields.io/pypi/dm/dcc-mcp-blender.svg?label=PyPI%20downloads)](https://pypi.org/project/dcc-mcp-blender/)
[![GitHub release downloads](https://img.shields.io/github/downloads/loonghao/dcc-mcp-blender/total.svg?label=release%20downloads)](https://github.com/loonghao/dcc-mcp-blender/releases)
[![GitHub Release](https://img.shields.io/github/v/release/loonghao/dcc-mcp-blender.svg)](https://github.com/loonghao/dcc-mcp-blender/releases)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov-blue.svg)](https://github.com/loonghao/dcc-mcp-blender/blob/main/pyproject.toml)
[![dcc-mcp-core](https://img.shields.io/badge/dcc--mcp--core-%3E%3D0.17.34-blue.svg)](https://github.com/loonghao/dcc-mcp-core)
[![Blender](https://img.shields.io/badge/Blender-3.6%20LTS%20%7C%204.2%20LTS%20%7C%204.3%20%7C%204.4-orange.svg)](https://www.blender.org/download/releases/)
[![MCP](https://img.shields.io/badge/MCP-2025--03--26-purple.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

`dcc-mcp-blender` turns Blender into a first-class MCP server. Once the addon is enabled, any MCP client (Claude Desktop, custom agents, etc.) can call Blender tools over HTTP without any external gateway.

```
┌─────────────────────────────────┐
│  Blender (Python 3.10+)         │
├─────────────────────────────────┤
│  dcc_mcp_blender                │
│  ├─ BlenderMcpServer            │
│  ├─ SkillCatalog (150+ tools)   │
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
- **150+ pre-built tools** — scene management, object manipulation, mesh/UV editing, rigging, pose libraries, interchange, materials, node graphs, rendering, physics, scripting and more
- **Extensible skill system** — drop new skill folders alongside built-ins or point to them via env vars
- **Main-thread host adapter** — GUI mode uses core `HostUiDispatcherBase` semantics through `BlenderUiDispatcher`; headless mode uses `BlenderHost` with a core `BlockingDispatcher`
- **Streamable HTTP transport** — compatible with any MCP 2025-03-26 client
- **Claude Desktop ready** — ship a one-line `mcpServers` config and you're done

---

## Available MCP Tools

| Category | Tools |
|---|---|
| **blender-scene** | `new_scene`, `open_scene`, `save_scene`, `list_objects`, `get_scene_info`, `get_session_info` |
| **blender-objects** | `create_object`, `delete_object`, `duplicate_object`, `move_object`, `rotate_object`, `scale_object`, `get_object_info`, `get_selection`, `set_selection`, `select_by_type`, `find_by_pattern`, `rename_object`, `parent_object`, `group_objects`, `set_visibility`, `get_bounding_box`, `center_origin`, `freeze_transforms` |
| **blender-mesh** | `add_modifier`, `apply_modifier`, `list_modifiers`, `get_mesh_info` |
| **blender-mesh-ops** | `get_poly_count`, `cleanup_mesh`, `triangulate_mesh`, `separate_mesh`, `combine_meshes`, `merge_vertices`, `extract_faces`, `mirror_mesh`, `select_by_material` |
| **blender-uv-ops** | `list_uv_maps`, `create_uv_map`, `delete_uv_map`, `copy_uv_map`, `get_uv_info`, `get_uv_islands`, `project_uvs`, `unwrap_uvs`, `pack_uvs`, `normalize_uvs` |
| **blender-rigging** | `create_armature`, `create_bone`, `mirror_bones`, `add_constraint`, `set_constraint_properties`, `bind_mesh_to_armature`, `add_shape_key`, `set_driver`, `retarget_animation` |
| **blender-pose-library** | `list_poses`, `save_pose`, `load_pose` |
| **blender-interchange** | `import_file`, `import_fbx`, `import_obj`, `export_gltf`, `export_usd`, `export_alembic`, `batch_export` |
| **blender-export-preset** | `list_export_presets`, `save_export_preset`, `load_export_preset`, `delete_export_preset` |
| **blender-shot-export** | `get_shot_info`, `export_camera` |
| **blender-materials** | `create_material`, `assign_material`, `set_material_color`, `list_materials`, `delete_material` |
| **blender-shader-nodes** | `list_material_nodes`, `set_principled_input`, `list_node_trees`, `list_nodes`, `create_node`, `delete_node`, `list_node_sockets`, `connect_nodes`, `disconnect_nodes`, `list_node_links`, `set_node_input`, `get_node_value`, `create_material_with_nodes`, `assign_texture_node`, `set_principled_inputs` |
| **blender-render** | `render_scene`, `set_render_settings`, `get_render_info`, `capture_viewport` |
| **blender-scripting** | `execute_python`, `execute_script_file`, `get_blender_info` |
| **blender-animation** | `set_keyframe`, `set_frame_range`, `get_frame_range`, `set_current_frame`, `get_keyframes`, `delete_keyframes`, `bake_animation` |
| **blender-lighting** | `create_light`, `set_light_properties`, `list_lights`, `set_world_background` |
| **blender-camera** | `create_camera`, `set_active_camera`, `set_camera_properties`, `list_cameras` |
| **blender-collection** | `create_collection`, `link_to_collection`, `list_collections` |
| **blender-geometry** | `create_sphere`, `save_blend`, `file_exists`, `export_fbx`, `export_obj` |
| **blender-geometry-nodes** | `add_geometry_nodes_modifier`, `list_geometry_nodes_modifiers`, `create_geometry_node_group`, `assign_geometry_node_group`, `set_geometry_node_modifier_input`, `evaluate_geometry_nodes_info` |
| **blender-physics** | `add_rigid_body`, `set_rigid_body_properties`, `remove_rigid_body`, `list_rigid_bodies`, `set_rigid_body_world_settings`, `bake_rigid_body_simulation`, `clear_rigid_body_bake`, `add_cloth_modifier`, `set_cloth_settings`, `add_collision_modifier`, `set_collision_settings`, `list_simulation_modifiers`, `bake_simulation`, `clear_simulation_cache`, `get_simulation_status` |

See [`src/dcc_mcp_blender/skills/SKILLS_INDEX.md`](src/dcc_mcp_blender/skills/SKILLS_INDEX.md) for staged loading guidance, task-to-skill chains, and side-effect profiles for all bundled skills.

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

In interactive add-on mode, `BlenderUiDispatcher` subclasses the shared core UI dispatcher and `BlenderTimerPump`
contains the Blender-specific `bpy.app.timers` wiring. In background mode, `BlenderHost` keeps using core
`BlockingDispatcher` with an explicit headless loop so automation does not depend on Blender UI timers.

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
