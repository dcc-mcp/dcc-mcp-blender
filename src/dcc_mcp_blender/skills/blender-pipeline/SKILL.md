---
name: blender-pipeline
description: "Blender asset build contracts, deterministic snapshots, metadata, project context, publish prep, and verified ComfyUI GLB publishing"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [blender, pipeline, metadata, publish, manifest, asset, build, snapshot, contract]
    search-hint: "asset build manifest, build contract, scene snapshot, compare rebuild, asset metadata, project context, publish manifest, prepare publish package, publish GLB to ComfyUI, local pipeline"
    search-aliases: [asset build, build contract, deterministic snapshot, compare scene, rebuild check, asset management, publishing, package prep, metadata management, project info, publish to disk, local delivery]
    intent: "Define repeatable Blender asset builds, capture deterministic scene state, manage local metadata, and prepare publish packages."
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
    produces: [file:manifest, file:snapshot, file:package, asset_build_contract, asset_metadata]
    requires: []
    tools: tools.yaml
---

# blender-pipeline

Local-only pipeline helpers for asset metadata and publish preparation.

This first version writes manifests and lightweight package directories on the
local filesystem only. It deliberately avoids studio-specific paths, service
names, hostnames, or external publishing integrations.

`publish_comfyui_asset` produces a verified GLB and `AssetDescriptor` without
contacting ComfyUI. The artifact works with official ComfyUI workflows; the
separate `dcc-mcp-comfyui` adapter can optionally stage it for latest-revision
sync when the `dcc_mcp_sync` node is installed.

`create_asset_build_manifest` stores a machine-readable contract on the active
scene and can also write it to JSON. The contract records intended parts,
armature controls, actions, reference approvals, delivery outputs, project
context, and a baseline scene snapshot. Chain it with
`blender-validation.validate_asset_build_manifest` before export or publish.

`capture_asset_snapshot` and `compare_asset_snapshot` provide a lightweight
rebuild check based on object, mesh, material, armature, action, transform, and
scene metadata. They avoid storing raw mesh data or image bytes.
