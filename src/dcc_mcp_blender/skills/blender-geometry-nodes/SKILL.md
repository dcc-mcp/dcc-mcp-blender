---
name: blender-geometry-nodes
description: "Blender Geometry Nodes group, modifier, and exposed input tools"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, geometry-nodes, node-graph, sockets, links, procedural, modifiers]
    search-hint: "geometry nodes modifier, procedural nodes, node group, modifier input, assign geometry node group"
    tools: tools.yaml
---

# blender-geometry-nodes

Typed tools for creating Geometry Nodes groups, assigning them to mesh
modifiers, setting exposed modifier inputs, and inspecting procedural graph
state. Use `blender-shader-nodes` for low-level shared node graph operations
such as `list_nodes`, `connect_nodes`, and `set_node_input`.
