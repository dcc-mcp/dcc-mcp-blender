---
name: blender-uv-ops
description: >-
  Blender authoring skill for UV maps, texture coordinate projection, unwraps,
  island inspection, packing, and normalization. Use this before falling back to
  blender-scripting whenever a task touches UVs or texture coordinates.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [blender, uv, texture, mesh, authoring]
    search-hint: >-
      uv map, texture coordinates, unwrap uv, smart project, planar projection,
      cube projection, uv islands, pack islands, normalize uv, copy uv map
    search-aliases: [UV editor, texture mapping, UV layout, seam unwrap, lightmap UV, UV channel, transfer UV, projection mapping]
    intent: "Create, inspect, and edit UV maps — unwrap, project, pack, normalize, and copy UV data for texture authoring."
    recall-context:
      app_type: blender
      domain: authoring
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
      targets: [uv_map, uv_island, mesh_data]
    produces: [uv_map, uv_island_list, normalized_coordinates]
    requires: []
    tools: tools.yaml
---

# blender-uv-ops

Typed UV authoring tools for Blender meshes. Load this skill when a workflow
needs UV maps, texture-coordinate projection, unwraps, UV island diagnostics,
packing, or normalization.

Prefer `blender-mesh` for topology and modifier work, `blender-materials` for
material slots, and `blender-shader-nodes` for shader graph edits. Use
`blender-scripting` only after checking this typed surface.
