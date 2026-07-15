# Blender Bundled Skills Index

This index helps agents choose typed Blender skills before falling back to raw Python. Load the narrowest skill that matches the task, then chain adjacent skills when a workflow crosses domains.

## Stage Map

| Skill | Stage | Purpose | Default-load policy | Side-effect profile | Discovery terms |
|---|---|---|---|---|---|
| `blender-scene` | bootstrap, scene, diagnostics | Start, open, save, list, and inspect scenes. | Load first for scene discovery or session checks. | Mixed: read-only inspection plus scene/file mutations. | session, scene info, open blend, save blend, list objects |
| `blender-objects` | scene, authoring | Create, delete, duplicate, transform, select, rename, group, parent, hide, bound, and inspect objects. | Load when object-level edits, selection, transforms, visibility, or bounds are requested. | Mutating except object info, selection reads, name searches, and bounds. | cube, object transform, duplicate, select, find, rename, parent, bounds |
| `blender-collection` | scene, organization | Create collections, link objects, and inspect collection structure. | Load when grouping or collection membership matters. | Mutating except collection listing. | collection, group, hierarchy, link object |
| `blender-mesh` | authoring, modeling | Add/apply/list modifiers and inspect mesh details. | Load when an existing mesh needs modifiers or mesh info. | Mutating except modifier and mesh inspection. | modifier, mesh info, apply, bevel, subdivision |
| `blender-mesh-ops` | authoring, modeling | Inspect, clean, triangulate, combine, separate, mirror, extract, and select polygon mesh data. | Load when topology or face-level mesh editing is requested. | Mutating except polygon count. | polygon count, cleanup mesh, triangulate, combine meshes, merge vertices, extract faces |
| `blender-uv-ops` | authoring, texture prep | Create, copy, inspect, project, unwrap, pack, and normalize UV maps. | Load when texture coordinates or UV islands are requested. | Mutating except UV-map and island inspection. | uv map, unwrap, texture coordinates, projection, pack islands |
| `blender-geometry` | authoring, interchange, pipeline | Create simple geometry and save/export blend, FBX, or OBJ files. | Load when file output or basic geometry helpers are needed. | Disk-writing and mutating except file existence checks. | sphere, export fbx, export obj, save blend, file exists |
| `blender-asset-source` | pipeline, source | Search filesystem and asset libraries for importable assets, returning validated `AssetDescriptor[]`. | Load before import when assets need discovery. | Read-only filesystem scan. | search assets, asset library, find 3D files, discover assets, asset source, browse files |
| `blender-extensions` | bootstrap, pipeline | Validate and install downloaded Blender Extensions or legacy add-on packages. | Load after a provider returns a local add-on package. | Writes to Blender's user extension/add-on directories and can enable installed code. | install extension, install addon, package zip, blender manifest, legacy addon |
| `blender-attributes` | authoring, metadata | Read, create, update, delete, and rename custom properties on Blender objects. | Load when object metadata, pipeline tags, or attribute CRUD is needed. | Mixed: read-only attribute listing plus mutating set/delete/rename. | custom property, attribute, object data, id property, metadata |
| `blender-interchange` | interchange, pipeline | Import FBX/OBJ/USD files and export GLTF, USD, Alembic, or batch export jobs. | Load when assets move between DCC/game/pipeline formats. | Disk-writing and scene mutation for imports. | import file, import fbx, import obj, import usd, export gltf, export usd, export alembic |
| `blender-import-to-scene` | interchange, pipeline, import | Consume an AssetDescriptor via ImportToSceneRequest, import the resolved FBX/OBJ/USD/glTF file into the active scene, and return ImportToSceneResult. | Load after an asset-source skill when a validated descriptor is ready. | Scene mutation for imports; disk-reading for file open. | import to scene, asset import, import fbx, import obj, import usd, import gltf, cross-dcc import |
| `blender-export-preset` | interchange, pipeline | Save, list, load, and delete reusable scene-stored export option presets. | Load when export settings need repeatable named presets. | Mutating except preset listing/loading. | export preset, batch export, reusable export options |
| `blender-shot-export` | interchange, shot | Inspect shot metadata and export camera metadata JSON. | Load for camera, shot, and animation delivery metadata. | Disk-writing except shot info. | shot export, camera metadata, frame range, camera json |
| `blender-validation` | pipeline, diagnostics | Run scene, mesh, material, animation, and export-readiness checks with severity-coded reports. | Load before export, publish, or package preparation. | Read-only diagnostics. | validation report, scene checks, mesh validation, export readiness, severity |
| `blender-pipeline` | pipeline, metadata, publish | Manage local asset metadata, project context, publish manifests, and lightweight publish packages. | Load for local publish preparation after validation passes or warnings are accepted. | Metadata mutation and local filesystem writes for manifests/packages. | asset metadata, project context, publish manifest, prepare package |
| `blender-materials` | authoring, lookdev | Create, assign, edit, list, and delete materials. | Load before shader nodes when material slots or colors are enough. | Mutating except material listing. | material, assign, color, shader base, delete material |
| `blender-shader-nodes` | authoring, node graph, lookdev | Inspect and edit shader/material node graphs plus shared node tree sockets, links, and values. | Load after materials when node-level shader edits or generic node graph operations are requested. | Mixed: read-only graph inspection plus node/link/socket mutations. | shader nodes, node graph, sockets, links, principled, texture node |
| `blender-material-library` | lookdev, pipeline, texture | Save/load portable material presets, inspect shader assignments, assign texture files, list/reload images, and set color management. | Load after basic materials when looks need reuse, texture files, or scene color-management state. | Mixed: preset/attribute/image mutations plus read-only inspection. | material preset, assign texture, shader assignment, image reload, color management |
| `blender-node-graph` | authoring, node graph, lookdev | Discover and inspect all node graph types (compositor, material, geometry) across the scene. | Load for cross-graph discovery or compositor tree inspection before falling back to shader/geometry-specific skills. | Read-only inspection. | compositor, all node graphs, node tree discovery, cross-graph, node graph inventory |
| `blender-texture-bake` | lookdev, texture, delivery | List bake targets and bake texture, ambient-occlusion, lighting, or transfer maps to explicit local paths. | Load after materials/UVs when generated texture outputs are needed. | Disk-writing bake operations; target listing is read-only. | texture bake, ambient occlusion, lighting bake, transfer maps, bake target |
| `blender-geometry-nodes` | authoring, node graph, procedural | Create Geometry Nodes groups, assign them to modifiers, set exposed inputs, and inspect procedural graph state. | Load for procedural geometry setup, modifier input updates, or geometry node group assignment. | Mixed: modifier/group creation plus read-only graph summaries. | geometry nodes, procedural, node group, modifier input, exposed socket |
| `blender-physics` | simulation, authoring | Add and tune rigid bodies, soft bodies, cloth, collision, force fields, particle systems, rigid body constraints, and simulation cache. Provides full Maya nCloth/nParticle/Bifrost/Field parity. | Load for any physics or dynamics setup — rigid/soft bodies, cloth, force fields, particles, constraints, simulation status, or cache bake/clear. | Mixed: read-only status/listing plus mutating setup, bake, and cache-clearing operations. | rigid body, soft body, cloth, collision modifier, force field, particle system, rigid body constraint, simulation cache, bake, mass, friction, physics, dynamics |
| `blender-expressions` | authoring, rigging, animation | Add, edit, and remove Blender drivers (scripted expressions, AVERAGE, SUM, MIN, MAX); manage driver variables; evaluate expression results. Maya expression editor / connection editor equivalent. | Load when driven properties, expression controllers, or driver variable bindings are needed. | Mixed: read-only driver listing/evaluation plus mutating driver/variable add/remove. | driver, expression, scripted expression, driver variable, evaluate driver, add driver, driven property, RNA driver |
| `blender-rigging` | authoring, animation | Create armatures and bones, add constraints, bind meshes, create shape keys, set drivers, and retarget compatible rigs. | Load for character setup, deformation rigs, constraints, drivers, shape keys, or retargeting. | Mutating. | rigging, armature, bones, constraints, drivers, shape keys, retargeting |
| `blender-pose-library` | authoring, animation | List, save, load, and mirror reusable armature poses stored on armature objects. | Load after rigging when pose capture or animation handoff needs reusable poses. | Mutating except pose listing. | pose library, save pose, load pose, mirror pose, armature pose |
| `blender-animation` | animation, shot | Set, inspect, delete, and bake keyframes plus frame ranges and current frame. | Load when timing, frame range, keyframe, curve inspection, deletion, or baking work starts. | Mutating except frame-range and keyframe reads. | keyframe, timeline, frame range, current frame, bake animation |
| `blender-camera` | shot, layout, render | Create cameras, set the active camera, edit camera properties, and list cameras. | Load when view, shot, or render framing is requested. | Mutating except camera listing. | camera, lens, active camera, shot, framing |
| `blender-lighting` | lookdev, render | Create lights, edit light properties, list lights, and set world background. | Load when visibility or render quality depends on lighting. | Mutating except light listing. | light, world background, sun, area light, exposure |
| `blender-light-rig` | lookdev, render, environment | Create reusable light rigs, softboxes, HDRI worlds, grouped light collections, and view-transform settings. | Load after basic lighting when scenes need repeatable studio or environment lighting. | Mutating except rig listing and summary. | three point light, softbox, hdri world, light rig, view transform, lighting summary |
| `blender-render` | render, diagnostics, delivery | Configure renders, render scenes, inspect render settings, and capture viewport images. | Load after scene/camera/lighting setup when output is needed. | Disk/output producing; read-only for render info. | render, viewport capture, image output, resolution |
| `blender-render-farm` | render, pipeline | Validate scenes, write job configs, submit to Deadline or Flamenco, and query farm job status. | Load after blender-render when distributed / farm rendering is needed. | Read-only for status/listing; network calls for submission/cancellation. | render farm, deadline, flamenco, distributed render, farm submission, job status |
| `blender-scene-assembly` | scene, pipeline, assembly | Merge .blend files, append/link data blocks, manage view layers, and inspect external references. | Load for multi-file assembly, library linking, layer management, or external reference inspection. | Mixed: read-only view layer/external ref inspection plus mutating merge/append/link operations. | merge scene, append blend, link blend, view layer, external reference, library linking |
| `blender-dev` | diagnostics, development | Inspect add-ons, Python environment, structured UI metadata, module reloads, debug listeners, and development entrypoints. | Load for adapter/add-on debugging before falling back to arbitrary scripting; avoid for normal scene authoring. | Mixed: read-only diagnostics plus explicit development code execution, path mutation, module reload, and add-on enable/disable. | addon diagnostics, reload modules, run check, debug server, UI snapshot, Python environment |
| `blender-attributes` | authoring | Create, read, update, delete, and rename custom properties (ID properties) on objects. | Load when custom property CRUD or attribute metadata is needed. | Mutating except attribute listing and reading. | custom property, attribute, object data, id property, metadata |
| `blender-node-graph` | authoring, node graph, lookdev | Discover all node graphs (material, geometry, compositor) and inspect compositor node trees. | Load for cross-graph discovery or compositor inspection before shader/geometry node edits. | Read-only graph introspection. | node graph, compositor nodes, all node graphs, cross-graph, node tree discovery |
| `blender-scene-assembly` | scene, pipeline, assembly | Merge .blend files, append/link data blocks, manage view layers, and inspect external references. | Load when assembling scenes from external files or managing view layers. | Mutating except view layer listing and external reference inspection. | merge scene, append blend, link blend, view layer, library linking, scene assembly |
| `blender-scripting` | diagnostics, escape hatch | Execute Python snippets or script files and inspect Blender runtime info. | Load last, after checking typed skills and only when custom logic is required. | Potentially arbitrary; use with explicit user intent. | python, script, custom, escape hatch, blender info |

## Common Task Chains

| Task | Preferred skill chain |
|---|---|
| Inspect a new session | `blender-scene` -> `blender-objects` -> `blender-mesh` |
| Build simple geometry | `blender-scene` -> `blender-objects` -> `blender-mesh` or `blender-geometry` |
| Edit polygon topology | `blender-objects` -> `blender-mesh-ops` -> `blender-mesh` if modifiers are needed |
| Prepare textured mesh UVs | `blender-mesh-ops` -> `blender-uv-ops` -> `blender-materials` |
| Character rig setup | `blender-objects` -> `blender-rigging` -> `blender-pose-library` -> `blender-animation` |
| Animation handoff | `blender-rigging` -> `blender-pose-library` -> `blender-animation` |
| Material setup | `blender-materials` -> `blender-shader-nodes` -> `blender-render` |
| Reusable lookdev | `blender-materials` -> `blender-shader-nodes` -> `blender-material-library` |
| Texture baking | `blender-materials` -> `blender-uv-ops` -> `blender-material-library` -> `blender-texture-bake` |
| Shader node graph edit | `blender-materials` -> `blender-shader-nodes` (`list_node_sockets` before `connect_nodes`/`set_node_input`) |
| Procedural node setup | `blender-objects` -> `blender-geometry-nodes` -> `blender-shader-nodes` for low-level graph edits -> `blender-render` |
| Physics setup | `blender-objects` -> `blender-mesh` -> `blender-physics` |
| Expression / driven property setup | `blender-rigging` or `blender-objects` -> `blender-expressions` |
| Full dynamics (cloth, particles, fields) | `blender-objects` -> `blender-physics` (add_cloth_modifier / add_particle_system / add_force_field) |
| Shot and render delivery | `blender-camera` -> `blender-lighting` or `blender-light-rig` -> `blender-render` |
| Distributed render farm | `blender-render` -> `blender-render-farm` (validate, write job, submit, monitor) |
| Studio lookdev setup | `blender-materials` -> `blender-material-library` -> `blender-light-rig` -> `blender-render` |
| Asset discovery and import | `blender-asset-source` -> `blender-interchange` (``import_file`` / ``import_fbx`` / ``import_obj`` / ``import_usd``) |
| Attribute CRUD on objects | `blender-objects` -> `blender-attributes` |
| Scene composition with external files | `blender-scene-assembly` -> `blender-collection` -> `blender-scene` |
| View layer management | `blender-scene-assembly` (``list_view_layers`` / ``create_view_layer`` / ``set_active_view_layer``) |
| Cross-graph node audit | `blender-node-graph` (``list_all_node_graphs``) -> `blender-shader-nodes` or `blender-geometry-nodes` |
| Compositor pipeline setup | `blender-node-graph` -> `blender-render` |
| File interchange | `blender-scene` -> `blender-interchange` -> `blender-export-preset` when settings repeat |
| Export validation | `blender-validation` -> `blender-interchange` -> `blender-export-preset` |
| Local publish prep | `blender-validation` -> `blender-pipeline` -> `blender-interchange` when files need export |
| Shot delivery | `blender-camera` -> `blender-animation` -> `blender-shot-export` -> `blender-interchange` |
| Add-on diagnostics | `blender-dev` -> `blender-scripting` only when no diagnostic helper fits |
| Custom fallback | Typed domain skill -> `blender-scripting` only for the missing operation |

## Loading Guidance

- Prefer typed skills for repeatable operations, structured errors, and MCP annotations.
- Use `blender-scene` for initial session and scene discovery.
- Load authoring skills only when the requested task enters that domain; prefer `blender-mesh-ops` for topology, `blender-mesh` for modifiers, and `blender-rigging`/`blender-pose-library` for character setup.
- Use `blender-shader-nodes` for graph-level socket/link edits; use `blender-materials` when material slots or simple colors are enough, `blender-material-library` for reusable looks, texture files, and color management, and `blender-geometry-nodes` when the workflow is about modifier assignment or exposed procedural inputs.
- Use `blender-texture-bake` only after mesh, UV, and material setup are explicit; prefer `dry_run` before writing bake outputs in automation.
- Use `blender-lighting` for individual lights and quick world color edits; use `blender-light-rig` for grouped three-point rigs, softboxes, HDRI worlds, and render view-transform coordination.
- Use `blender-interchange` and `blender-shot-export` for import/export and delivery before writing custom Python exporters.
- Use `blender-validation` before interchange/export or publish prep, and use `blender-pipeline` for Blender-native metadata and local manifests/packages.
- Use `blender-attributes` for object custom property CRUD when pipeline metadata, tagging, or attribute inspection is needed.
- Use `blender-node-graph` for cross-graph discovery and compositor tree inspection; switch to `blender-shader-nodes` or `blender-geometry-nodes` for detailed per-graph editing.
- Use `blender-scene-assembly` for multi-file composition, library linking, and view layer management after basic scene setup is done.
- Use `blender-dev` for add-on/runtime diagnostics, structured UI metadata, module reloads, and reproducible development entrypoints before reaching for arbitrary Python.
- Use `blender-expressions` for driver/expression work — adding/editing/removing drivers and driver variables. Prefer it over `blender-rigging` for standalone expression controller tasks, and over raw scripting for driven property bindings.
- Use `blender-physics` for all dynamics and simulation work — rigid bodies, soft bodies, cloth, force fields, particle systems, and rigid body constraints. It now provides full parity with Maya's nCloth, nParticle, nHair, Bifrost, and Fields.
- Keep `blender-scripting` as the final escape hatch; mention which typed skills were checked first.
- Treat disk-writing, render, and scripting tools as higher-risk operations and ask for explicit paths or intent when needed.
