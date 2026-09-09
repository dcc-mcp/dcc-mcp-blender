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
      inspect mesh components, vertex coordinates, edge adjacency, face normals
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

### Solid pointed arches

`create_pointed_arch` creates a closed, all-quad U-shaped solid for deep door
and window surrounds. Load the `modeling` group first. `width` is the clear
opening, `spring_height` is the jamb height, `rise` is the pointed head rise,
`frame_width` is horizontal jamb / vertical crown thickness, and `depth` is
physical reveal depth. Curved head thickness is not a constant normal offset.
The opening bottom center is the origin; X spans width, Z height, and the
solid occupies Y=0 through Y=depth. Use object transforms to orient it on a
side wall. The tool leaves selection and active object unchanged, rejects
existing names, and does not cut the wall behind the opening, create glass,
assign material, bevel, or unwrap UVs. Follow with the corresponding typed
tools. Recess the glazing and cut the wall separately so the depth remains
visible; a coplanar opaque wall can hide the entire reveal.

## Component discovery

Use `inspect_mesh_components` before choosing vertex, edge, or face indices.
It reads the original mesh in Object mode without changing selection or mode.
Coordinates, centroids, and normal filters are object-local, not evaluated or
world-space. The optional bounds filter tests each component's centroid.

Pages contain at most 256 records. Pass `next_offset` and the returned
`revision` as `expected_revision` for subsequent pages, with unchanged filters.
The token covers mesh identity, coordinates, normals and connectivity; any
change rejects stale paging. Discard indices after edits. Existing mutation
tools do not yet consume this query token, so it is not a mutation guard.

The scan rejects meshes above 100,000 total vertices/edges/faces/loops.
Connectivity lists are capped at 64 entries per relation, with full counts and
`connectivity_complete=false` when truncated. A rejected scan never returns
a partial revision. For example, query faces with `normal_direction=[0,0,1]`
and `normal_min_dot=0.9` to find locally upward-facing faces.
