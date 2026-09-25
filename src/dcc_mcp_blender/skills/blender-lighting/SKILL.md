---
name: blender-lighting
description: "Blender lighting — create, configure and manage lights and world background"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: lookdev
    version: "1.0.0"
    tags: [blender, lighting, lights, world, light-linking]
    search-hint: "create light, point, sun, area, spot, energy, color, world background, environment lighting, list lights, light linking, receiver, blocker"
    search-aliases: [create light, point light, sun light, area light, spot light, set light color, light energy, world color, environment lighting, list lights, light linking, exclude light from object, block light]
    recall-context:
      app_type: blender
      domain: lookdev
      workflow_stage: authoring
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      creates: true
      modifies: true
      targets: [light, world_background]
    produces: [light, world_background, lighting_setup]
    requires: []
    tools: tools.yaml
---

# blender-lighting

Blender lighting management skill.

## Lighting detail

`create_light` and `set_light_properties` cover the basics. This one covers
per-object control:

| Tool | Description |
|---|---|
| `set_light_linking` | Restrict a light to a receiver collection, with an optional blocker collection |

It is version dependent and does not silently no-op:

- **Light linking lives on the object**, as `Object.light_linking`, not on the
  light data block. Objects that expose no such property are refused with that
  reason instead of writing to a property that does not exist.
- Both collections are resolved before either is assigned, so a missing
  collection cannot leave the light half-linked.
- It affects Cycles and EEVEE Next and does not change the light's energy.

IES profiles are not exposed here. Blender has no `Light.ies_file` property, so
attaching one means building an IES node in the light's shader tree, which this
skill does not do yet.
