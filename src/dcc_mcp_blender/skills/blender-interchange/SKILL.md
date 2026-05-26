---
name: blender-interchange
description: >-
  Blender interchange skill for typed FBX/OBJ imports, GLTF/USD/Alembic exports,
  and repeatable batch exports. Use for moving assets between DCC, game, and
  pipeline tools before falling back to scripting.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: interchange
    version: "1.0.0"
    tags: [blender, interchange, import, export, fbx, obj, gltf, usd, alembic, pipeline]
    search-hint: >-
      import file, import fbx, import obj, export gltf, export usd, export alembic,
      batch export, interchange, pipeline, game export
    tools: tools.yaml
---

# blender-interchange

Typed import/export tools for Blender scene interchange. Load this skill when a
workflow needs asset import, GLTF/USD/Alembic export, or batch export. Existing
`blender-geometry` exposes FBX/OBJ export names and delegates to the same
implementation.

Prefer `blender-export-preset` for reusable export settings, `blender-shot-export`
for camera/shot metadata, and `blender-scripting` only after checking typed
interchange tools.
