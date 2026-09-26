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
    tags: [blender, lighting, lights, world, light-linking, ies]
    search-hint: "create light, point, sun, area, spot, energy, color, world background, environment lighting, list lights, light linking, receiver, blocker, IES profile, photometric, light shader"
    search-aliases: [create light, point light, sun light, area light, spot light, set light color, light energy, world color, environment lighting, list lights, light linking, exclude light from object, block light, IES profile, ies file, photometric light, gobo, light falloff]
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

`create_light` and `set_light_properties` cover the basics. These cover the rest:
per-object control and real-world light distribution.

| Tool | Description |
|---|---|
| `set_light_linking` | Restrict a light to a receiver collection, with an optional blocker collection |
| `set_light_ies` | Shape a light with an IES photometric profile, or remove one |

### Light linking

It is version dependent and does not silently no-op:

- **Light linking lives on the object**, as `Object.light_linking`, not on the
  light data block. Objects that expose no such property are refused with that
  reason instead of writing to a property that does not exist.
- Both collections are resolved before either is assigned, so a missing
  collection cannot leave the light half-linked.
- It affects Cycles and EEVEE Next and does not change the light's energy.

### IES profiles

`set_light_ies` attaches a photometric file to a light. Blender has no
`Light.ies_file` property, so this is **not** a property assignment: it builds a
`ShaderNodeTexIES` in the light's shader tree and wires its `Fac` output to the
emission node's `Strength` input.

Three things decide whether the profile actually reaches the render, and all
three are verified by reading the tree back rather than assumed:

- **The node must drive the emission node the renderer reads.** A light tree can
  hold several emission nodes; only the one feeding `ShaderNodeOutputLight`
  lights anything, so the link is traced back from the output rather than taken
  from the first match.
- **The profile file must exist.** Blender accepts a path it cannot open and then
  renders the light unshaped, so the path is checked before it is used and a
  missing file is refused.
- **The `Vector` input is left unconnected.** The renderer resolves the profile
  direction from the light itself; connecting a geometry direction there
  mis-aims the beam.

Version handling is explicit, not a `hasattr` guess: a build below the supported
baseline, or one that cannot create the node type, is refused with that reason
instead of reporting success.

Photometric files are read as supplied. Two file-level details change the result
and neither is reported by Blender, so they are worth knowing when a profile
renders as nothing:

- A file with a **single horizontal angle** gives Blender a zero-width horizontal
  range and reads as black in every direction. Rotational symmetry has to be
  expressed by repeating one vertical distribution across all horizontal angles.
- **Photometric type B rotates the frame**, so the beam stops following the
  lamp's aim. Type A and C files keep the profile aligned with the lamp.
