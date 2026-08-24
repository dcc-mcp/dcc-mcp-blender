---
name: blender-mesh-ops
description: >-
  Blender authoring skill for verified cross-DCC modeling verbs, polygon mesh
  inspection, cleanup, topology mutation, UV generation, material assignment,
  hierarchy, and modifier workflows. Use this before falling back to
  blender-scripting whenever a workflow models or edits mesh topology.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [blender, mesh, polygon, topology, modeling]
    search-hint: >-
      mesh topology, polygon count, cleanup mesh, triangulate, combine meshes,
      create primitive, loft sections, lathe profile, extrude faces, bevel edges,
      inset faces, boolean, edge loop, array instances, mirror, pivot, freeze transforms,
      auto UV, UV projection, assign material, select by material
    search-aliases: [polygon edit, hard surface modeling, fuselage loft, revolve profile, rotor array, pivot origin, mesh cleanup, topology fix, UV projection, material binding]
    intent: "Build and verify polygon models through the shared cross-DCC modeling vocabulary."
    recall-context:
      app_type: blender
      domain: authoring
      workflow_stage: modeling
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: true
      creates: true
      deletes: true
      targets: [mesh_data, polygon, vertex]
    produces: [mesh_data, polygon_count, topology_report]
    requires: []
    tools: tools.yaml
    groups: groups.yaml
---

# blender-mesh-ops

Typed polygon modeling and mesh editing tools for Blender. The lightweight
`mesh-edit` group remains active by default. The larger `modeling` group is
inactive until requested and covers the shared DCC verbs for primitive,
loft/lathe, hard-surface edits, modifiers, pivots, hierarchy, cleanup, UVs, and
material assignment. Mutating modeling tools read Blender state back before
reporting success.

Prefer `blender-objects` for object transforms and selection, `blender-mesh` for
modifier management, `blender-uv-ops` for UVs, and `blender-scripting` only
after checking this typed surface.
