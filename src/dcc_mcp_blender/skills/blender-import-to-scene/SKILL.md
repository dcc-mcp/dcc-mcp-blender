---
name: blender-import-to-scene
description: >-
  Blender cross-DCC asset import skill — consumes an AssetDescriptor, opens the
  asset file in Blender, and returns an ImportToSceneResult. Use as the
  receiving end of the asset import pipeline after an asset-source skill
  resolves the descriptor.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: import
    version: "1.0.0"
    tags: [blender, asset-import, pipeline, destructive]
    search-hint: >-
      import to scene, asset import, import asset, import fbx, import obj,
      import usd, import gltf, import glb, cross-dcc import, asset descriptor
    search-aliases: [import to scene, asset import, import asset, cross dcc import, import descriptor, blender import]
    intent: "Import an asset described by an AssetDescriptor into the active Blender scene and return an ImportToSceneResult."
    recall-context:
      app_type: blender
      domain: io
      workflow_stage: import
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
      targets: [scene_node]
    produces: [scene_node, import_result]
    requires:
      - asset-source
    tools: tools.yaml
---

# blender-import-to-scene

Blender asset import skill that consumes a validated `AssetDescriptor` from
the shared `dcc_mcp_core.asset_import` contract and imports the asset file into
the active Blender scene. Returns a typed `ImportToSceneResult` with imported
node names and any non-fatal warnings.

Load this skill after `asset-source` resolves the descriptor.

## Tools

| Tool | Category | Description |
|------|----------|-------------|
| `import_to_scene` | Import | Import an asset from an AssetDescriptor into the active Blender scene |

## Gateway flow

```
search_skills("asset import") → load_skill("asset-source") → call("search_assets", {query: "table"})
→ AssetDescriptor → load_skill("blender-import-to-scene") → call("import_to_scene", {descriptor: ...})
→ ImportToSceneResult
```
