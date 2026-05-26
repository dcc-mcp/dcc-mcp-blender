---
name: blender-material-library
description: "Blender material presets, shader assignments, texture images, and color-management helpers"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, material, lookdev, texture, color-management, preset]
    search-hint: "material presets, assign texture, material connections, shader assignment, color management, images"
    tools: tools.yaml
---

# blender-material-library

Reusable look-development helpers for Blender scenes.

Material presets use the portable `dcc-mcp-blender.material-preset.v1` JSON
shape stored on the scene, and texture helpers operate on explicit local image
paths only. No private asset-library paths, services, or hostnames are assumed.
