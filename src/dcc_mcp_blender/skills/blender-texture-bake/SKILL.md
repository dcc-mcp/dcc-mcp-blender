---
name: blender-texture-bake
description: "Blender texture, lighting, ambient-occlusion, and transfer-map baking helpers"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: lookdev
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

## High-to-low projection controls

`transfer_maps` accepts optional `cage_extrusion`, `max_ray_distance`, `use_cage`,
and `normal_space` overrides. Distances are in Blender scene units, not a fixed
millimeter unit; `max_ray_distance: 0` means unlimited. For example, in a
meter-scale scene, use `use_cage: true`, `cage_extrusion: 0.02`,
`max_ray_distance: 0.05`, and `normal_space: TANGENT` for an extruded cage reaching
20 mm outward and rays limited to 50 mm. Choose distances for the actual mesh:
this is not a universal preset. Existing custom cage objects/settings remain
Blender's responsibility; this tool does not create or validate custom cages.

Omitted options preserve the previous Blender behavior, rather than silently
choosing projection defaults. `bake_settings.projection_overrides` reports only
explicit overrides, including in dry runs. They are passed to the bake operator,
not saved into scene bake settings; the temporary render engine is restored on
success or failure. The existing target image/material and selection behavior
is unchanged. Interpret normal textures as non-color data when using them.

Only an operator result of `FINISHED` is saved; cancellation or an exception
returns a failure without saving that map. A completed bake confirms execution, not coverage or visual quality. Check UVs,
source/target alignment, normals and projection distances. A uniform tangent
normal map may be correct for flat geometry, so uniform pixels are not an error.
