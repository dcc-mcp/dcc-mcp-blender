---
name: blender-pipeline
description: "Blender local asset metadata, project context, publish manifests, and package prep"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, pipeline, metadata, publish, manifest, asset]
    search-hint: "asset metadata, project context, publish manifest, prepare publish package, local pipeline"
    search-aliases: [asset management, publishing, package prep, metadata management, project info, publish to disk, local delivery]
    intent: "Manage local asset metadata, project context, publish manifests, and lightweight publish packages for pipeline delivery."
    recall-context:
      app_type: blender
      domain: pipeline
      workflow_stage: publish
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: true
      file_output: true
      targets: [file:manifest, file:package, scene_metadata]
    produces: [file:manifest, file:package, asset_metadata]
    requires: []
    tools: tools.yaml
---

# blender-pipeline

Local-only pipeline helpers for asset metadata and publish preparation.

This first version writes manifests and lightweight package directories on the
local filesystem only. It deliberately avoids studio-specific paths, service
names, hostnames, or external publishing integrations.
