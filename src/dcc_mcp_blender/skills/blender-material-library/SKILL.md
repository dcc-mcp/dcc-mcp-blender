---
name: blender-material-library
description: "Blender material presets, shader assignments, texture images, and color-management helpers"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: lookdev
    version: "1.0.0"
    tags: [blender, material, lookdev, texture, color-management, preset]
    search-hint: "material presets, assign texture, material connections, shader assignment, color management, images"
    search-aliases: [material library, lookdev, PBR preset, texture assignment, color space, image texture, shader connections, material template, reusable material]
    intent: "Manage reusable material presets, texture image assignments, shader connections, and color-management settings."
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
      targets: [material, texture, shader_node]
    produces: [material_preset, texture_assignment, color_config]
    requires: []
    tools: tools.yaml
---

# blender-material-library

Reusable look-development helpers for Blender scenes.

Material presets use the portable `dcc-mcp-blender.material-preset.v1` JSON
shape stored on the scene, and texture helpers operate on explicit local image
paths only. No private asset-library paths, services, or hostnames are assumed.

## Image lifecycle

`list_images` and `reload_image` report on images already loaded. These own
where an image actually lives:

| Tool | Description |
|---|---|
| `load_image` | Load a file from disk into the datablock set |
| `save_image` | Write a datablock back to disk |
| `pack_image` / `unpack_image` | Embed into the .blend, or write out and stop embedding |
| `image_file_status` | Where it lives: packed, external, missing, unsaved, or modified |
| `list_image_tiles` | UDIM tiles; a non-UDIM image reports one tile |

Notes that matter in practice:

- Packing is confirmed, not assumed: if the pack call leaves nothing packed the
  tool fails rather than reporting success for an embed that did not happen.
  Packing an already packed image is a no-op that says so.
- `save_image` works under `blender --background`, where an image loaded from
  disk has no decoded pixels until one is actually read.

  Two things make it work, and both are deliberate:

  1. **It never assigns `image.filepath`.** Under background mode that re-associates
     the datablock with the file and invalidates the decoded pixel buffer. Assigning
     before the decode leaves `pixels` empty (IndexError on read); assigning after it
     makes `save()` fail with "does not have any image data". No ordering works, so
     the assignment is simply not done.

  2. **It decodes by indexing `image.pixels[0]`,** then checks `has_data`.

  With a `file_path` it writes via `save_render(path)`, which writes to an explicit
  path without re-pointing the datablock. Without one it writes in place via
  `image.save()`. Either way it confirms the file exists afterwards, so a save that
  writes nothing is a failure rather than a success.

  Two notes: `len(image.pixels)` is not a usable probe, because on every supported
  version it already reports the full pixel count while `has_data` is still False.
  And `save_render` applies scene color management, so it is not byte-identical to
  `image.save()`; it is the only viable route for "save a copy at this path".

  Only images loaded from disk need the decode. Generated images already carry
  pixel data and save directly. Packing needs none of this because it copies the
  source file.
- `save_image` needs a path for generated images, which have none, and reports
  that instead of guessing a location.
- A colour space the running Blender refuses is returned in `not_applied`
  rather than dropped, so a caller can see the assignment did not stick.
- Pack and unpack move files; neither deletes image data.
