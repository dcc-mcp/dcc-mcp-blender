# Blender capability coverage

Coverage means discoverable, typed operations with verified state readback and
usable workflow tests. A tool name, generic Python execution, successful mock,
or exported file's existence alone does not establish workflow coverage.
This ledger describes the baseline at `9a4971d` and the work still required;
it does not mark an entire phase complete when a single slice lands.

## Delivery phases

| Phase | Deliverables | Status |
| --- | --- | --- |
| 0: acceptance baseline | Current LTS CI/Python/README; nonempty real-host test evidence; truthful library discovery; version/context-aware discovery; Windows gateway CLI acceptance | In progress |
| 1: existing workflows | Mesh component inspection and revision-guarded edits; UV seam/pin/island/UDIM editing; Geometry Nodes interfaces, attributes and evaluated geometry; asset dependency inspection | Pending implementation and native acceptance |
| 2: character and procedural workflows | Action Slots/NLA/curve editing; bone constraints, weights, real retargeting; native Curves/Hair; scoped simulation configuration and cache jobs | Pending; current-version Action read/delete compatibility is only a first slice |
| 3: missing domains | Sculpt/Paint; Grease Pencil; VSE; tracking/masking; dedicated Compositor workflows | Pending implementation and native acceptance |
| 4: end-to-end benchmarks | Mesh-to-export, character-to-bake, and shot-to-final-media through the supported gateway/CLI route | Pending; requires preceding capabilities |

Each implementation PR must add tool metadata, positive and negative tests,
native host tests where applicable, readback, and concise usage guidance.
Version-specific unavailable capabilities must report that state explicitly.
Long-running operations require bounded admission, status, cancellation and
terminal artifact validation. Existing unrelated worktrees remain independent.

## Domain gaps

| Domain | Existing foundation | Remaining workflow coverage |
| --- | --- | --- |
| Mesh modeling | Primitives, extrude/inset/bevel, boolean, loop/loft/lathe, transforms, cleanup | Bounded components/adjacency/selection, revision-safe references, retopology |
| Curve and other geometry | Object creation and generic node editing | Control points/handles, surfaces/text/lattice/metaballs, native Curves authoring |
| UV | Map CRUD, projection, unwrap, islands, packing | Seams/pins, island edits, UDIM, density and overlap/stretch validation |
| Sculpt | Generic execution only | Brush/stroke, masks, face sets, remesh and multiresolution workflows |
| Texture/vertex/weight paint | Texture baking and image assignment | Typed targets/layers/strokes, weight repair and saved-result verification |
| Geometry Nodes | Groups, modifiers, graph edits, input values | Interface CRUD, geometry attributes, zones and evaluated geometry |
| Hair/Curves | Generic execution only | Surface attachment, grooming, interpolation, simulation/cache |
| Rigging | Armatures/bones, binding, pose library, basic constraints | Pose-bone constraints, weights, IK/FK, cross-rig/rest-space retargeting |
| Animation | Keying, sample bake, read/delete | Action/Slot management, NLA, F-curve edits and retiming |
| Physics | Rigid body, cloth/collision and cache operations | Scoped safe caches, fluid domain/flow/effector, Dynamic Paint, new physics |
| Look development/render | Materials, lights, HDRI, OCIO, passes, render jobs | AOV/light-group workflows, multi-engine validation and recovery |
| Compositor | Generic node graph operations | Dedicated media/pass-to-output graph workflows and artifact validation |
| Grease Pencil | Generic execution only | Objects, layers, drawings, strokes, materials/modifiers and 2D animation |
| Video Sequencer | Generic execution only | Video/audio strips, transitions, retiming, proxies and encoding |
| Tracking and masks | Generic execution only | Markers, solving, lens distortion, masks and reprojection-error evidence |
| Asset Browser/publishing | File search, append/link, metadata/manifests | Native assets/catalogs/tags/previews, overrides, dependencies and portable publishing |
| Discovery/context | Skill and capability manifests | Complete/unavailable distinction, version/context requirements, bounded live schema |

UV quality, multi-view render, scoped simulation and material validation PRs
may improve individual rows; review their actual merged tests before updating
coverage. Do not duplicate another open PR or infer completion from its title.

## Acceptance tiers

1. Unit/schema: invalid inputs, bounded outputs, revisions and side effects.
2. Native host: official Blender 5.2.1/4.5.13, factory-startup fixtures, explicit
   executed/passed/skipped counts; failure is not converted into a skip.
3. Transport: initialize/discover/call/error/job contracts on the actual server.
4. Workflow: shared gateway `search -> describe -> call`, terminal receipts,
   reopened exports or decoded render/media artifacts, and required GUI checks.

GUI acceptance uses the project DCC-CUA/UI Control route with process/window
binding. Background fixtures must not modify a user's active scene. Windows,
Linux and macOS results must remain distinguishable; one cannot stand in for
the others. Re-run the relevant gates against the final PR head after changes.

## Benchmark completion criteria

- **Mesh to export:** create/edit components, unwrap and validate UVs, assign
  materials, export and reimport; compare geometry, UV and material semantics.
- **Character to bake:** build/bind a small rig, edit weights/constraints,
  animate through slots/NLA, bake and evaluate poses at known frames.
- **Shot to final media:** configure a scoped simulation, inspect terminal
  cache state, render known frames/passes, composite/edit and decode output.

Record software/Core/CLI versions, tool routes, timings, retries, terminal
errors and product evidence. Raw-Python fixture setup must be separated from
the typed operations being accepted. No benchmark is complete at this baseline.
