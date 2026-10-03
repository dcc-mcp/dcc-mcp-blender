---
name: blender-materials
description: "Blender material system — create, assign, modify, list, and exchange MaterialX materials"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: lookdev
    version: "1.1.0"
    tags: [blender, materials, shading, materialx]
    search-hint: "create material, assign, color, shader, PBR, list materials, delete material, materialx, mtlx, export mtlx, import mtlx"
    search-aliases: [create material, new material, assign material, set material color, list materials, remove material, material slots, shader base, materialx, mtlx, export materialx, import materialx, standard surface]
    intent: "Create, assign, edit, list, and delete materials in the Blender scene with color and shader property control."
    recall-context:
      app_type: blender
      domain: lookdev
      workflow_stage: authoring
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      creates: true
      modifies: true
      deletes: true
      targets: [material, material_slot]
    produces: [material, material_slot, color_assignment, materialx_document]
    requires: []
    tools: tools.yaml
---

# blender-materials

Blender material management skill.


For existing material metallic/roughness edits, load `blender-shader-nodes`
and use `set_principled_inputs` with `material_name` and
`inputs: {"Metallic": 0.94, "Roughness": 0.28}`. Use `list_node_sockets` to inspect
the target node and its linked sockets first; a linked socket's default value
does not replace its upstream shader. Material creation already accepts PBR
values; do not recreate an existing material just to change its roughness.

## MaterialX round-trip

`export_materialx` writes Principled BSDF socket values to a `.mtlx` document as
a `standard_surface` shader, and `import_materialx` reads `standard_surface`,
`open_pbr_surface` and `usd_preview_surface` documents back into Principled BSDF
materials. Both directions carry values only: a socket driven by an upstream node
is reported under `linked_inputs` / `connected_inputs` and keeps its default
value, so textures and node graphs are never silently baked or dropped.
