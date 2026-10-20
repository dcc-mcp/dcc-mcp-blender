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
    version: "1.2.0"
    tags: [blender, materials, shading, materialx, faces]
    search-hint: "create material, assign, color, shader, PBR, list materials, delete material, materialx, mtlx, export mtlx, import mtlx, per-face materials, polygon material index"
    search-aliases: [create material, new material, assign material, set material color, list materials, remove material, material slots, shader base, materialx, mtlx, export materialx, import materialx, standard surface, face materials, polygon materials, material index]
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
      targets: [material, material_slot, polygon_material_index]
    produces: [material, material_slot, color_assignment, materialx_document, face_material_assignment]
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


## Bounded per-face materials

`assign_material` fills an object material slot; it does not assign that slot to
polygons. For multi-material meshes:

1. Create materials and fill the required slots using `assign_material`.
2. Call `inspect_face_materials(object_name, offset=0, limit=64)` to discover
   the original polygon assignments, effective slot names, and `revision`.
3. Call `assign_face_materials` with that `expected_revision` and explicit
   `assignments: [{"face_index": 0, "material_index": 0},
   {"face_index": 1, "material_index": 1}]`.
4. Inspect subsequent pages with `next_offset` and the same revision. After
   save/reopen or GLB export/reimport, inspect anew and compare material names
   and face groups, not session-local revisions or exported polygon ordering.

Bounds: 4096 assignments per call, 256 faces per inspection page, 1024 material
slots, and 100000 total original mesh vertices/edges/polygons/loops scanned for
the revision. Names are exact; no active-object fallback. Empty meshes can be
inspected but not assigned. Missing/empty slots, duplicate faces (even identical
assignments), invalid indices including booleans, and stale revisions fail
before mutation. The revision pins object/mesh identity, topology/coordinates,
and effective slot identities, but excludes face assignments, so a repeated
successful batch is idempotent. It is not a material-assignment concurrency token.

Both tools require Object mode and preserve selection, active object and mode.
Assignment additionally refuses shared mesh data and linked/overridden/read-only
objects or meshes; make them explicitly single-user/local first. No materials or
slots are created or reordered, and unrequested polygons remain unchanged.
These tools inspect the original mesh, not modifier-evaluated or exported faces.

Success returns exact assignments, affected/changed counts and
`postcondition.verified: true` after exact readback.
On a write failure, every original polygon index is restored where possible and
then read back. `rollback_verified: true` means indices and the geometry/slot
revision match the preflight state; only then is `mutation_applied: false` reported.
`mutation_applied: true` means a remaining change was observed; `null` means the
state could not be verified. An unverified rollback is not atomic success: stop
and inspect before continuing. Error codes are in `context.error_code`.
