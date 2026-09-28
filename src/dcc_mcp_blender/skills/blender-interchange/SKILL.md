---
name: blender-interchange
description: >-
  Blender interchange skill for typed FBX/OBJ/USD imports, GLTF/USD/Alembic exports,
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
    tags: [blender, interchange, import, export, fbx, obj, usd, gltf, alembic, pipeline]
    search-hint: >-
      import file, import fbx, import obj, import usd, export gltf, export usd, export alembic,
      batch export, interchange, pipeline, game export
    search-aliases: [import USD, import FBX, import OBJ, export GLTF, export USD, export Alembic, export glb, batch export, asset interchange, file format conversion, game export, gltf vertex count, glb vertex count mismatch, vertex split normals uv]
    intent: "Import FBX/OBJ/USD files into Blender and export scenes to GLTF, USD, Alembic, or batch formats for DCC and game pipelines."
    recall-context:
      app_type: blender
      domain: io
      workflow_stage: interchange
      task_category: import
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      creates: true
      modifies: true
      imports: true
      exports: true
      file_output: true
      targets: [scene_node, file:fbx, file:obj, file:usd, file:gltf, file:abc]
    produces: [file:fbx, file:obj, file:usd, file:gltf, file:abc, scene_node]
    requires: []
    tools: tools.yaml
---

# blender-interchange

Typed import/export tools for Blender scene interchange. Load this skill when a
workflow needs asset import (FBX, OBJ, USD), GLTF/USD/Alembic export, or batch
export. Existing `blender-geometry` exposes FBX/OBJ export names and delegates
to the same implementation.

## Tools

| Tool | Category | Description |
|------|----------|-------------|
| `import_file` | Import | Import FBX or OBJ files with format auto-detection |
| `import_fbx` | Import | Import FBX files with Blender's FBX importer |
| `import_obj` | Import | Import OBJ files with Blender's OBJ importer |
| `import_usd` | Import | Import USD files (.usd/.usda/.usdc/.usdz) with typed options — meshes, materials, cameras, lights, textures |
| `export_gltf` | Export | Export to GLTF/GLB for game engines and web (see GLTF export vertex counts) |
| `export_usd` | Export | Export to USD for pipeline interchange |
| `export_alembic` | Export | Export to Alembic with optional frame range |
| `batch_export` | Export | Run multiple exports with optional preset |

Prefer `blender-export-preset` for reusable export settings, `blender-shot-export`
for camera/shot metadata, and `blender-scripting` only after checking typed
interchange tools.

## GLTF export vertex counts

A glTF/GLB file stores one vertex per unique normal + UV combination, so an
exported asset systematically reports **more vertices than the shared-vertex
count Blender shows for the same mesh**. A mismatch is expected behavior, not an
export defect.

- **Why:** hard edges and flat shading split each corner into one vertex per
  face normal. A default cube is 8 vertices in Blender and 24 in GLB (3x),
  because each of the 8 corners carries 3 hard-edge normals.
- **Rule of thumb:** hard-edged / flat-shaded meshes multiply the most
  (typically 2x-4x); smooth-shaded meshes approach 1x.
- **Measured example:** a 3-part Blender white-clay model reported 554 vertices
  in-host and 2200 in GLB (~4x): cube 8 -> 24, sphere 482 -> 1984,
  cylinder 64 -> 192.

`export_gltf` returns no vertex / face / material metrics, so compare counts on
the exported asset: re-import it with `import_file` and inspect it with
`get_mesh_info`, run `blender-validation` checks such as `validate_mesh` and
`validate_export_readiness`, or use an external glTF validator. Never treat
"GLB vertex count differs from host vertex count" as a failure on its own.
