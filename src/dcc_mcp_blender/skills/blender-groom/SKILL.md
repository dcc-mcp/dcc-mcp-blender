---
name: blender-groom
description: >-
  Blender guide-curve grooming for imported character meshes. Create
  deterministic surface-attached hair guides, inspect generated grooms, and
  tune width, length, color, and roughness.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [blender, groom, hair, curves, guide-curves, character, surface-attachment]
    search-hint: >-
      groom hair guide curves hairstyle scalp attach hair strands curve width
      hair material tuck shorten imported head character grooming
    search-aliases: [hair groom, curve groom, guide hair, attach hair to scalp, hairstyle, hair strands, tuck hair]
    intent: "Create and edit deterministic Blender guide curves on an imported scalp mesh before lookdev or export."
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

This skill is the Blender-side stage after an external generator such as the
Hyper3D marketplace skill returns an FBX or GLB. It creates one editable curve
object containing many poly splines. Roots are placed on source mesh vertices,
so every generated strand has a deterministic attachment point and can be
shortened or widened without losing its root.

## Workflow

1. Use the installed `hyper3d` skill with `create_rodin_task` and up to five
   labeled reference views when a three-view head asset is needed.
2. Wait with `get_task_status`, then call `download_assets` with the returned
   `task_uuid` and `subscription_key`.
3. Import the downloaded FBX through `blender-import-to-scene` or
   `blender-interchange.import_fbx`.
4. Call `create_groom_guides` on the scalp mesh. Keep the generated groom in a
   separate collection so the imported head remains easy to inspect. For a
   complete head mesh, use `root_height_min` and `root_height_max` to limit
   roots to the upper normalized local-Z region and avoid the face or neck.
5. Call `set_groom_style` for width, color, roughness, or root-preserving
   length changes. Use `inspect_grooms` for readback before saving or exporting.

The skill provides deterministic guide curves and material controls. Full
strand simulation, collision, and cache baking remain separate capabilities.
