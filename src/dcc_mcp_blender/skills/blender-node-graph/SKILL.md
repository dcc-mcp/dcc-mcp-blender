---
name: blender-node-graph
description: "Blender node graph introspection — compositor nodes, cross-graph discovery (material, geometry, compositor)"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, node-graph, compositor, nodes, shader, geometry-nodes]
    search-hint: "node graph, compositor nodes, material nodes, geometry nodes, all node graphs, node tree discovery"
    search-aliases: [compositor, all node graphs, cross-graph, node tree overview, compositor node tree, shader nodes, geometry nodes list]
    intent: "Introspect all Blender node graph types (compositor, material, geometry) and expose compositor-specific node tree information."
    recall-context:
      app_type: blender
      domain: authoring
      workflow_stage: lookdev
      task_category: read_only
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: false
      creates: false
      targets: []
    produces: [node_graph_inventory]
    requires: ["blender-shader-nodes", "blender-geometry-nodes"]
    tools: tools.yaml
---

# blender-node-graph

Typed tools for broad node graph introspection — discovering all node graphs
in the scene (material, geometry, compositor) and inspecting the compositor
node tree specifically. For detailed shader or geometry node editing, use
`blender-shader-nodes` or `blender-geometry-nodes` respectively.

## Tools

| Tool | Description |
|---|---|
| `list_all_node_graphs` | Discover all node graphs (material, geometry, compositor) in the scene |
| `get_compositor_node_tree` | Return the full compositor node tree (nodes + links) |
| `list_compositor_nodes` | List nodes in the compositor node tree |

## Common workflows

- **Scene node graph audit**: `list_all_node_graphs` -> drill into specific graphs
- **Compositor inspection**: `get_compositor_node_tree` for full graph overview
- **Cross-graph discovery**: understand all active node trees before targeted editing
