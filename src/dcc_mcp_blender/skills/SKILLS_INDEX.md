# Blender Bundled Skills Index

This index helps agents choose typed Blender skills before falling back to raw Python. Load the narrowest skill that matches the task, then chain adjacent skills when a workflow crosses domains.

## Stage Map

| Skill | Stage | Purpose | Default-load policy | Side-effect profile | Discovery terms |
|---|---|---|---|---|---|
| `blender-scene` | bootstrap, scene, diagnostics | Start, open, save, list, and inspect scenes. | Load first for scene discovery or session checks. | Mixed: read-only inspection plus scene/file mutations. | session, scene info, open blend, save blend, list objects |
| `blender-objects` | scene, authoring | Create, delete, duplicate, transform, and inspect objects. | Load when object-level edits or transforms are requested. | Mutating except object info. | cube, object transform, duplicate, move, rotate, scale |
| `blender-collection` | scene, organization | Create collections, link objects, and inspect collection structure. | Load when grouping or collection membership matters. | Mutating except collection listing. | collection, group, hierarchy, link object |
| `blender-mesh` | authoring, modeling | Add/apply/list modifiers and inspect mesh details. | Load when an existing mesh needs modifiers or mesh info. | Mutating except modifier and mesh inspection. | modifier, mesh info, apply, bevel, subdivision |
| `blender-uv-ops` | authoring, texture prep | Create, copy, inspect, project, unwrap, pack, and normalize UV maps. | Load when texture coordinates or UV islands are requested. | Mutating except UV-map and island inspection. | uv map, unwrap, texture coordinates, projection, pack islands |
| `blender-geometry` | authoring, interchange, pipeline | Create simple geometry and save/export blend, FBX, or OBJ files. | Load when file output or basic geometry helpers are needed. | Disk-writing and mutating except file existence checks. | sphere, export fbx, export obj, save blend, file exists |
| `blender-materials` | authoring, lookdev | Create, assign, edit, list, and delete materials. | Load before shader nodes when material slots or colors are enough. | Mutating except material listing. | material, assign, color, shader base, delete material |
| `blender-shader-nodes` | authoring, node graph, lookdev | Inspect material nodes and edit Principled BSDF inputs. | Load after materials when node-level shader edits are requested. | Mixed: read-only node listing plus shader mutations. | shader nodes, principled, metallic, roughness, sockets |
| `blender-geometry-nodes` | authoring, node graph, procedural | Add and list Geometry Nodes modifiers and node groups. | Load for procedural geometry setup or node modifier inspection. | Mixed: modifier creation plus read-only listing. | geometry nodes, procedural, node group, modifier input |
| `blender-physics` | simulation, authoring | Add, edit, and remove rigid-body physics settings. | Load for rigid-body setup after objects or mesh creation. | Mutating. | rigid body, collision, mass, friction, physics |
| `blender-animation` | animation, shot | Set keyframes, frame ranges, and the current frame. | Load when timing, frame range, or keyframe work starts. | Mutating except frame-range reads. | keyframe, timeline, frame range, current frame |
| `blender-camera` | shot, layout, render | Create cameras, set the active camera, edit camera properties, and list cameras. | Load when view, shot, or render framing is requested. | Mutating except camera listing. | camera, lens, active camera, shot, framing |
| `blender-lighting` | lookdev, render | Create lights, edit light properties, list lights, and set world background. | Load when visibility or render quality depends on lighting. | Mutating except light listing. | light, world background, sun, area light, exposure |
| `blender-render` | render, diagnostics, delivery | Configure renders, render scenes, inspect render settings, and capture viewport images. | Load after scene/camera/lighting setup when output is needed. | Disk/output producing; read-only for render info. | render, viewport capture, image output, resolution |
| `blender-scripting` | diagnostics, escape hatch | Execute Python snippets or script files and inspect Blender runtime info. | Load last, after checking typed skills and only when custom logic is required. | Potentially arbitrary; use with explicit user intent. | python, script, custom, escape hatch, blender info |

## Common Task Chains

| Task | Preferred skill chain |
|---|---|
| Inspect a new session | `blender-scene` -> `blender-objects` -> `blender-mesh` |
| Build simple geometry | `blender-scene` -> `blender-objects` -> `blender-mesh` or `blender-geometry` |
| Prepare textured mesh UVs | `blender-mesh` -> `blender-uv-ops` -> `blender-materials` |
| Material setup | `blender-materials` -> `blender-shader-nodes` -> `blender-render` |
| Procedural node setup | `blender-objects` -> `blender-geometry-nodes` -> `blender-render` |
| Physics setup | `blender-objects` -> `blender-mesh` -> `blender-physics` |
| Shot and render delivery | `blender-camera` -> `blender-lighting` -> `blender-render` |
| File interchange | `blender-scene` -> `blender-geometry` |
| Custom fallback | Typed domain skill -> `blender-scripting` only for the missing operation |

## Loading Guidance

- Prefer typed skills for repeatable operations, structured errors, and MCP annotations.
- Use `blender-scene` for initial session and scene discovery.
- Load authoring skills only when the requested task enters that domain.
- Keep `blender-scripting` as the final escape hatch; mention which typed skills were checked first.
- Treat disk-writing, render, and scripting tools as higher-risk operations and ask for explicit paths or intent when needed.
