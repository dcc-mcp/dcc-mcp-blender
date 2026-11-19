---
name: blender-photographic-materials
description: "Physical toy materials, PBR projection, alpha leaves, and millimetre edge finishing"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: lookdev
    version: "1.0.0"
    tags: [blender, material, toy, pbr, bevel, alpha, translucency, lookdev]
    search-hint: "painted toy material, gloss black eyes, scanned PBR, box projection, alpha leaves, translucency, toy bevel, millimetre bevel"
    search-aliases: [photographic material, toy shader, painted plastic, black eye material, plant leaf material, scans, box projected textures, edge bevel]
    intent: "Configure and validate physical toy materials and edge finishing for photographically rendered Blender shots."
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
      targets: [material, shader_node, image, bevel_modifier]
    produces: [photographic_material, pbr_texture_graph, toy_bevel, material_validation_report]
    requires: [blender-materials, blender-shader-nodes, blender-mesh-ops]
    tools: tools.yaml
---

# blender-photographic-materials

This skill packages the material contract for real-toy shots.

- `configure_photographic_material` creates or updates painted toy, gloss-black eye, and plant-leaf materials. Optional diffuse, roughness, and OpenGL / GL normal paths use local object-space box projection with blend 0.25. The PBR validator also verifies that each loaded map is connected to the Principled BSDF. Pass `texture_source: "Poly Haven"` when the maps come from the required scan library so the complete shot validator can verify provenance metadata.
- Painted toys use Principled roughness 0.48, coat weight 0.25, coat roughness 0.3, and a scale 900 noise bump with 0.03 strength and 0.2 mm distance.
- Gloss-black eyes use roughness 0.08, coat weight 1.0, and coat roughness 0.03.
- Plant leaves use alpha cutout nodes, an alpha-capable surface mode, and a small subsurface contribution.
- `configure_toy_bevel` keeps a render-visible three-segment bevel between 0.3 and 0.7 mm and limits it to no edge subset.
- `validate_photographic_material` is read-only and reports missing shader, texture, alpha, translucency, or bevel contract details. With `require_pbr_textures`, it verifies named Poly Haven diffuse, roughness, and OpenGL normal maps, their Principled BSDF links, Object-coordinate box projection, and the 0.25 projection blend.

Use local downloaded scan files explicitly. The skill does not assume a network asset service.
