---
name: blender-shot-export
description: >-
  Blender shot export skill for camera metadata and shot frame-range delivery.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: interchange
    version: "1.0.0"
    tags: [blender, shot, camera, export, animation, interchange]
    search-hint: >-
      shot export, camera export, camera metadata, shot info, frame range,
      animation delivery
    search-aliases: [shot delivery, camera JSON, export camera data, shot metadata, render camera, animation export, frame metadata]
    intent: "Inspect shot metadata and export camera/frame-range data as structured JSON for downstream shot and delivery pipelines."
    recall-context:
      app_type: blender
      domain: io
      workflow_stage: delivery
      task_category: query
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: false
      file_output: true
      targets: [file:json]
    produces: [file:json, shot_info, camera_metadata]
    requires: []
    tools: tools.yaml
---

# blender-shot-export

Typed shot/camera metadata helpers for delivery workflows. Use with
`blender-camera`, `blender-animation`, and `blender-interchange` when exporting
shots or camera handoff data.
