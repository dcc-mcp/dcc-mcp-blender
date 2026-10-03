---
name: blender-portable-scene
description: Save a new self-contained native scene copy with relative render output and file-browser path metadata audited for publication. Use only for an explicitly authorized task-owned scene.
license: MIT
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: interchange
    version: "1.0.0"
    tools: tools.yaml
    tags: [blender, publish, native, paths, portable]
    search-hint: publish portable self-contained native blend copy private path metadata
---

# Self-contained scene copy

This bounded tool accepts a task-authorized output root and never overwrites an existing file. Output paths reject symlinks and reparse points. It temporarily clears file-browser directory metadata, makes render output Blender-relative, and saves an uncompressed copy into a staging directory. A conservative path-string scan must pass before atomic no-clobber file publication. The active scene's render and browser settings are restored. It rejects external libraries, texts, clips, sounds, volumes/caches, movie or sequence images, unpacked file images, non-built-in fonts, sequence editors, complex modifiers, object drivers, and script or IES nodes in material/world/light trees and node groups. It is not an arbitrary-scene sanitizer or a general secret detector. Asset licences and intentional public metadata still require review. Reopen the delivered copy through native tools, compare geometry/material/animation state and render it before calling the source package accepted.
