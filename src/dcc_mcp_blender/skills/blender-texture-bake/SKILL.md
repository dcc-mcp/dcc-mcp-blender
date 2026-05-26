---
name: blender-texture-bake
description: "Blender texture, lighting, ambient-occlusion, and transfer-map baking helpers"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, bake, texture, lighting, ambient-occlusion, transfer-map]
    search-hint: "texture bake, bake ambient occlusion, bake lighting, transfer maps, bake targets"
    tools: tools.yaml
---

# blender-texture-bake

Local texture baking helpers for Blender meshes.

Tools require explicit local output paths or directories and return structured
map names, planned files, written files, warnings, and bake settings. Use
`dry_run` when validating bake plans in automation before committing to a render.
