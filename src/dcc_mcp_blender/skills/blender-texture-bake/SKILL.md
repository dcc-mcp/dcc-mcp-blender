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
    search-aliases: [bake maps, render to texture, AO bake, lightmap, curvature bake, normal bake, cavity map, bake target discovery]
    intent: "Bake texture maps including ambient occlusion, lighting, and transfer maps from high-to-low poly meshes."
    recall-context:
      app_type: blender
      domain: lookdev
      workflow_stage: texture_prep
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
      targets: [image_texture, file:image]
    produces: [file:image, bake_result, map_list]
    requires: []
    tools: tools.yaml
---

# blender-texture-bake

Local texture baking helpers for Blender meshes.

Tools require explicit local output paths or directories and return structured
map names, planned files, written files, warnings, and bake settings. Use
`dry_run` when validating bake plans in automation before committing to a render.
