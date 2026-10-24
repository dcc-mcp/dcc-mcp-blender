---
name: blender-compositor
description: "Blender compositing setup and node graph editing — enable the compositor, build trees, add nodes, connect sockets, and set values"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: render
    version: "1.0.0"
    tags: [blender, compositor, compositing, node-graph, nodes, post-processing, denoise, cryptomatte]
    search-hint: "compositor, compositing, node tree, render layers, composite node, denoise, glare, cryptomatte, file output, post process"
    search-aliases: [compositing, compositor node, compositor tree, enable compositor, connect compositor nodes, post processing, render layers, viewer node, glare, denoise, cryptomatte, z combine]
    intent: "Enable and author Blender compositor node graphs — create trees, add and delete nodes, connect or disconnect sockets, and set socket values."
    recall-context:
      app_type: blender
      domain: authoring
      workflow_stage: render
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.5,<5.3"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: true
      creates: true
      targets: [compositor_node_tree, compositor_node, node_link]
    produces: [node_list, socket_info, link_list, node_type_catalog]
    requires: ["blender-node-graph"]
    tools: tools.yaml
---

# blender-compositor

Typed tools for authoring Blender's compositor. `blender-node-graph` stays the
read-only discovery surface (`list_all_node_graphs`, `list_compositor_nodes`,
`get_compositor_node_tree`); this skill adds the write half — enabling the
compositor, building a starter tree, and creating, wiring, and tuning nodes.

Node types are addressed by Blender id, UI label, or alias
(`CompositorNodeDenoise`, `Denoise`, and `denoise` all resolve to the same
node). Call `list_compositor_node_types` when unsure.

## Tools

| Tool | Description |
|---|---|
| `setup_compositor_tree` | Enable render compositing and optionally build Render Layers -> native output |
| `set_compositor_enabled` | Toggle the version-appropriate compositor switch without changing the graph |
| `clear_compositor_tree` | Clear this scene; on 5.0–5.2, rebind a new empty group and preserve the old datablock |
| `create_compositor_node` | Create a compositor node (id, label, or alias) |
| `delete_compositor_node` | Delete a compositor node by name |
| `connect_compositor_nodes` | Connect an output socket to an input socket |
| `disconnect_compositor_nodes` | Disconnect links by id or endpoints |
| `set_compositor_node_value` | Set an input socket default value |
| `get_compositor_node_value` | Read one socket value or all socket values |
| `list_compositor_node_links` | List every link in the compositor tree |
| `list_compositor_node_types` | Discover supported compositor node ids, labels, and aliases |

## Common workflows

- **Enable compositing**: `setup_compositor_tree` -> `list_compositor_nodes`
- **Denoise pass**: `setup_compositor_tree` -> `create_compositor_node(denoise)` -> `connect_compositor_nodes`
- **Cryptomatte matte**: `create_compositor_node(cryptomatte)` -> `connect_compositor_nodes` -> `set_compositor_node_value`
- **Tune a filter**: `create_compositor_node(glare)` -> `set_compositor_node_value` -> `list_compositor_node_links`

Every tool accepts an optional `scene_name`; the active scene is used when it is omitted.


## Version and ownership boundaries

- Blender 4.5 uses `scene.node_tree`, `scene.use_nodes`, and `CompositorNodeComposite`.
- Blender 5.0–5.2 uses `scene.compositing_node_group`, `scene.render.use_compositing`,
  and the active `NodeGroupOutput` with a first **Color** output interface socket.
  The deprecated `scene.use_nodes` setter is not used on this branch.
- Blender 5.3+ has a different effects-stack API and is rejected by this slice,
  rather than silently treating it as 5.2. The package's minimum host remains 4.5.
- Reads of a 5.0–5.2 group do not enable rendering. The result key `use_nodes`
  remains for compatibility and reports effective enabled state, not the deprecated RNA value.
- In-place writes reject linked/override data and groups with multiple users.
  `clear_compositor_tree` and `setup_compositor_tree(clear=true)` replace only the
  selected scene's group binding; the old group is retained, even when no longer used.
- Catalogue entries report host-resolved `id`, `legacy_id` when renamed, and RNA
  `registered` status. Registration alone is not proof that a node can be used in
  the target tree. Unsupported node creation returns an error and removes staged data.
- This change covers tree ownership, output routing, enable state, and known node-id
  aliases. It does not implement the separate 5.x File Output settings migration.

Official reference: [Blender 5.0 compositor migration](https://developer.blender.org/docs/release_notes/5.0/migration/compositor_migration/).
Native regression scenarios live in `tests/e2e/test_compositor_e2e.py`; API-shape
mocks alone do not establish native host support or rendered-pixel correctness.
