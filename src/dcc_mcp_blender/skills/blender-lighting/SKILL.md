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
    tags: [blender, lighting, lights, world, IES, light-linking]
    search-hint: "create light, point, sun, area, spot, energy, color, world background, environment lighting, list lights, IES profile, light linking, receiver, blocker"
    search-aliases: [create light, point light, sun light, area light, spot light, set light color, light energy, world color, environment lighting, list lights, IES texture, photometric light, light linking, exclude light from object, block light]
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

`create_light` and `set_light_properties` cover the basics. These two cover
real-world falloff and per-object control:

| Tool | Description |
|---|---|
| `set_light_ies` | Attach an IES profile to a spot light and set its strength |
| `set_light_linking` | Restrict a light to a receiver collection, with an optional blocker collection |

Both are version or light-type dependent, and neither silently no-ops:

- **IES is spot lights only.** A point, sun, or area light is rejected. Lights
  with no `ies_file` property report that IES is unavailable on that build
  rather than accepting a path that is then ignored.
- **Light linking needs Blender 4.1+.** Pre-4.1 lights have no `light_linking`
  property, so the tool refuses with that reason instead of writing to a
  property that does not exist.
- Both affect Cycles and EEVEE Next; neither changes the light's energy.
