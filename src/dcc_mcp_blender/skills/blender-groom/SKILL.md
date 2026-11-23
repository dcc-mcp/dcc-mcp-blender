---
name: blender-groom
description: >-
  Blender guide-curve grooming for imported character meshes. Create
  deterministic surface-attached hair guides, shape and thin generated grooms,
  inspect them, create variants, and manage their lifecycle.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [blender, groom, hair, curves, guide-curves, character, surface-attachment, comb, taper, density]
    search-hint: >-
      groom hair guide curves hairstyle scalp attach hair strands curve width
      hair material tuck shorten imported head character grooming comb taper thin duplicate validate roots
    search-aliases: [hair groom, curve groom, guide hair, comb hair, taper hair, thin groom, attach hair to scalp, hairstyle, hair strands, tuck hair]
    intent: "Create, shape, inspect, validate, and manage deterministic Blender guide curves on an imported scalp mesh before lookdev or export."
    recall-context:
      app_type: blender
      domain: character
      workflow_stage: authoring
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=3.6"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      creates: true
      modifies: true
      deletes: true
      targets: [curve_object, hair_material]
    produces: [groom_guides, groom_metadata, hair_material]
    requires: []
    tools: tools.yaml
---

# blender-groom

This skill is the Blender-side stage after an external asset-generation skill
returns a validated AssetDescriptor for an FBX or GLB. It creates one editable
curve object containing many NURBS splines. Roots are placed on source mesh
vertices, so every generated strand has a deterministic attachment point and
can be shortened or widened without losing its root.

## Workflow

1. Obtain a validated `AssetDescriptor` from the selected external
   asset-generation skill. Provider-specific submission, status, and download
   operations belong to that skill, not to this Blender-side skill.
2. If the upstream provider operation fails, stop the workflow and return the
   provider error. Do not create a procedural substitute or switch generators
   until the user explicitly confirms that fallback is allowed.
3. Import the asset through `blender-import-to-scene` or
   `blender-interchange.import_fbx`.
4. Call `create_groom_guides` on the scalp mesh. Keep the generated groom in a
   separate collection so the imported head remains easy to inspect. For a
   complete head mesh, use `root_height_min` and `root_height_max` to limit
   roots to the upper normalized local-Z region and avoid the face or neck.
5. Call `shape_groom_guides` for comb direction, length, curl, or tip taper.
6. Call `set_groom_style` for width, color, roughness, or root-preserving length
   changes. Use `inspect_grooms` for readback before saving or exporting.
7. Use `validate_groom_attachment` after editing or moving the source mesh. Use
   `thin_groom_guides`, `duplicate_groom`, and `delete_groom` for guide density,
   hairstyle variants, and generated-output cleanup.

The skill provides deterministic guide curves and material controls. Full
strand simulation, collision, and cache baking remain separate capabilities.
