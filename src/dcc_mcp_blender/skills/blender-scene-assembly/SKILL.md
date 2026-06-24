---
name: blender-scene-assembly
description: "Blender scene assembly — merge .blend files, append/link data blocks, manage view layers and external references"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, scene-assembly, merge, append, link, view-layers, references]
    search-hint: "merge scene, append blend, link blend, view layer, external reference, library linking, scene assembly"
    search-aliases: [merge, append, link, reference, library, layer, scene composition, assembly pipeline, blender assembly, scene merge]
    intent: "Assemble Blender scenes by merging external files, appending/linking data blocks, and managing view layers and library references."
    recall-context:
      app_type: blender
      domain: scene
      workflow_stage: pipeline
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
      targets: [scene, collection, data_block, library]
    produces: [assembled_scene, view_layer_config, linked_references]
    requires: []
    tools: tools.yaml
---

# blender-scene-assembly

Typed tools for assembling Blender scenes — merging data from external .blend
files, appending or linking specific data block types, managing view layers,
and inspecting library references. Mirrors Maya's scene assembly surface.

## Tools

| Tool | Description |
|---|---|
| `merge_scene` | Merge all data from an external .blend into the current scene |
| `append_from_blend` | Append specific data block types (objects, collections, etc.) |
| `link_from_blend` | Link data blocks as library references |
| `list_view_layers` | List view layers in a scene |
| `create_view_layer` | Create a new view layer |
| `remove_view_layer` | Remove a view layer |
| `set_active_view_layer` | Set the active view layer |
| `list_external_references` | List all external .blend file references |

## Common workflows

- **Scene composition**: `merge_scene` to combine multiple .blend files
- **Selective import**: `append_from_blend` with targeted data types
- **Library workflow**: `link_from_blend` for shared assets -> `list_external_references`
- **Layer management**: `list_view_layers` -> `create_view_layer` / `set_active_view_layer`
