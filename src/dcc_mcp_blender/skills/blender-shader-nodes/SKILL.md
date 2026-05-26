---
name: blender-shader-nodes
description: "Blender shader and shared node graph editing tools"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, shader-nodes, geometry-nodes, node-graph, sockets, links, materials, procedural]
    search-hint: "shader nodes, material nodes, node graph, sockets, links, principled bsdf, texture node, geometry node tree"
    tools: tools.yaml
---

# blender-shader-nodes

Typed tools for inspecting and editing Blender node graphs. Use the material
helpers for common shader workflows, and the shared `node_tree_ref` tools for
node creation, sockets, links, and socket values before falling back to custom
Python.
