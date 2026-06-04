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
    search-aliases: [node editor, shader graph, material graph, create node, connect nodes, set socket, principled shader, BSDF, texture input, geometry nodes modifier]
    intent: "Inspect and edit Blender shader/compositing/geometry node graphs — create nodes, connect sockets, set values, and manage node trees."
    recall-context:
      app_type: blender
      domain: lookdev
      workflow_stage: lookdev
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
      targets: [node_tree, shader_node, material]
    produces: [node_tree, node_list, socket_info, link_list]
    requires: []
    tools: tools.yaml
---

# blender-shader-nodes

Typed tools for inspecting and editing Blender node graphs. Use the material
helpers for common shader workflows, and the shared `node_tree_ref` tools for
node creation, sockets, links, and socket values before falling back to custom
Python.
