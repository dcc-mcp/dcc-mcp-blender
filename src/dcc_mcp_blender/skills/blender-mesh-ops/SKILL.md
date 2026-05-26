---
name: blender-mesh-ops
description: >-
  Blender authoring skill for polygon mesh inspection, cleanup, topology
  mutations, mesh extraction, mirroring, and material-based face selection. Use
  this before falling back to blender-scripting whenever a workflow edits mesh
  topology directly.
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
      separate mesh, merge vertices, extract faces, mirror mesh, select by material
    tools: tools.yaml
---

# blender-mesh-ops

Typed polygon mesh editing tools for Blender. Load this skill when an existing
mesh needs topology inspection, cleanup, combine/separate operations, face
extraction, vertex merging, mirroring, or material-based face selection.

Prefer `blender-objects` for object transforms and selection, `blender-mesh` for
modifier management, `blender-uv-ops` for UVs, and `blender-scripting` only
after checking this typed surface.
