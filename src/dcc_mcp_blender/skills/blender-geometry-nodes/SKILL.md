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
    search-aliases: [geonodes, procedural modeling, node modifier, node group, exposed inputs, procedural mesh, geometry node tree, GN modifier]
    intent: "Create and manage Blender Geometry Nodes groups, assign them as modifiers, and set exposed input values."
    recall-context:
      app_type: blender
      domain: authoring
      workflow_stage: authoring
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
      targets: [node_group, modifier, mesh_object]
    produces: [geometry_nodes_group, modifier]
    requires: []
    tools: tools.yaml
---

# blender-geometry-nodes

Typed tools for creating Geometry Nodes groups, assigning them to mesh
modifiers, setting exposed modifier inputs, and inspecting procedural graph
state. Use `blender-shader-nodes` for low-level shared node graph operations
such as `list_nodes`, `connect_nodes`, and `set_node_input`.
