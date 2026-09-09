---
name: blender-geometry-nodes
description: "Blender Geometry Nodes groups, modifiers, exposed inputs, and revision-guarded interface socket editing"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, geometry-nodes, node-graph, sockets, links, procedural, modifiers]
    search-hint: "geometry nodes modifier, procedural nodes, node group, modifier input, assign geometry node group, interface socket create update remove, socket identifier and default"
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

## Interface socket workflow (Blender 4.0+)

Use `inspect_geometry_node_interface` to read socket identifiers, directions,
basic defaults, the group-user count and an interface revision. The query
rejects interfaces over 256 items or text fields over 1024 UTF-8 bytes; it does
not return a partial revision.
Blender 3.6 reports `interface_api_unavailable` for these new tools.

Pass the exact revision to `create_geometry_node_socket`,
`update_geometry_node_socket`, or `remove_geometry_node_socket`. Updates and
removal require the returned identifier, not a potentially ambiguous label.
Read back after each edit and use the new revision. Stale revisions fail before
editing; never drop the guard or retry with guessed identifiers.

Creation supports Geometry, Float, Int, Bool, Vector, Color, and String socket
types in either direction. Updates preserve identity and can change the name,
description, or a supported basic default. Numeric defaults are finite within
`+/-1000000`; vectors have three components and colors have four. Names are
limited to 63 UTF-8 bytes; descriptions and string defaults to 1024 bytes.
Use `set_geometry_node_modifier_input` for an individual modifier's input
value; changing a group interface default is not a per-object override.

Interface edits affect **all users of the group**. Linked/library-override
groups are refused by these mutating tools. Removing a socket can disconnect
links and discard per-instance inputs. After a native edit starts, a failure
reports possible mutation and no rollback; inspect before retrying.

The process-local revision covers the queried interface layout, labels,
directions, types, descriptions and supported basic defaults, not evaluated
geometry, links or per-modifier values. Panel CRUD, socket-type replacement,
object/material/collection references, menus, field-domain controls and zones
remain outside this first interface slice. The graph-info tool does not
prove that evaluated geometry matches the intended result.

The implementation uses Blender's [NodeTreeInterface API](https://docs.blender.org/api/current/bpy.types.NodeTreeInterface.html).
