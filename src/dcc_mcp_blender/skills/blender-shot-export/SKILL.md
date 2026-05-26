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
    tools: tools.yaml
---

# blender-shot-export

Typed shot/camera metadata helpers for delivery workflows. Use with
`blender-camera`, `blender-animation`, and `blender-interchange` when exporting
shots or camera handoff data.
