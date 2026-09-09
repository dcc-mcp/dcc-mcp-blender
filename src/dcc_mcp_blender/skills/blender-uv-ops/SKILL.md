---
name: blender-uv-ops
description: >-
  Blender authoring skill for UV maps, texture coordinate projection, unwraps,
  island inspection, quality audits, SVG layout export, packing, and normalization. Use this before falling back to
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
      cube projection, uv islands, pack islands, normalize uv, copy uv map, audit UV overlap, degenerate UV, export UV layout SVG
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


## Quality and delivery

Use `audit_uv_layout` with explicit mesh names (up to 4096) for source mesh
quality checks. It does not evaluate modifiers or silently switch out of Edit
Mode. `success` means the query ran; require both `context.complete` and
`context.passed` for a clean result for the enabled checks (reported in
`context.checks`); disabling overlap is not a complete quality acceptance.
Budget limits are shared by the entire
request; `complete=false` requires a narrower request or a larger budget.
Counts for degeneracy, tile bounds and overlap are triangle counts/pairs,
not unique polygons. Face indices in the bounded detail list locate problems.
`per_object` overlap is the default; choose `selection` only when those objects
must share a non-overlapping atlas. Exact coincident triangle stacks (including
mirrors) are allowed only with `allow_stacked=true`. UV distortion and texel
density are not measured. `udim` permits tile crossings and validates only the
nonnegative ten-column coordinate domain, not texture-file availability.

Use `export_uv_layout` to write actual polygon UV edges to a new SVG path.
Each object gets its own labelled panel, fitted to its coordinates with the
unit-tile border shown; panels do not imply shared texel scale. Export is a
layout visualization, not a quality pass. It neither packs nor repairs UVs.
