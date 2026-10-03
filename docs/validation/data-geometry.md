# Data-first geometry acceptance

This draft adds `blender-data-geometry`: bounded mesh creation, native editable POLY-curve creation, and original-geometry fingerprint inspection. Existing names are rejected; selection is preserved; no code evaluation, imports, arbitrary attributes or file IO are exposed by these tools.

## Verification

- Input-contract tests cover finite values, names, indices, repeated indices, cardinality, coordinate bounds, dimensions, booleans and the2MB aggregate payload budget
- Focused lint/format checks pass
- Real MCP SDK2.2.0 with Core/server0.20.39: discovery, native quad creation, native extruded curve creation, save and reopen
- A larger QGIS handoff used ten actual exported elevation bands, creating29 editable contour objects plus the source board and survey curve. Native original-geometry hashes, counts, material links and transforms were read before/after saving and reopening and compared exactly
- Genuine Cycles CPU render completed. These measurements do not validate manifoldness, correct hole winding, engineering tolerances or continuous-terrain reconstruction. Those require separate checks

## Host/version boundary

The source handoff was based on main c04e990 (official adapter0.2.13, supported Blender4.5+); the publication branch preserves updated public main 2075cec, including the separately merged MaterialX/USD changes. The cloud source-qualification host has Blender4.3.2. The new capability files were therefore exercised as an explicitly recorded development backport on official adapter0.1.43, which supports that host. The whole current adapter and its4.5 gate were not bypassed. Target4.5/5.2 native acceptance remains a review/CI item; the4.3 run is not presented as current-main acceptance or an officially released feature.

The installed4.3 build lacks OpenImageDenoise. The first lookdev render failed explicitly; a separate unchanged official typed denoise-control backport disabled that unavailable option before the successful render. That rendering compatibility operation is not part of the new geometry capability.

## Reproduction

Discover/load `blender-data-geometry`, call `create_mesh_from_data` with four XYZ vertices and a quad, or `create_curve_from_points` with a closed local-XY ring and bounded extrusion. Inspect with `inspect_data_geometry`, save using the existing scene tool, reopen and inspect again. Compare float32 coordinate and topology fingerprints. For curves with interior rings preserve source winding and review the evaluated fill visually. Transform and material tools remain separate; optional existing material_name on a curve uses the named native material, never a guessed or created one.

## Source qualification snapshot

The handed-off source's complete default unit/contract lane passed1,504tests with34skips on Core/server0.20.41. Its46 focused data/text/skill-structure tests also passed. Repository-prescribed lint, format and skill validation passed. Current-Core native creation and four negative mutation guards are independently recorded in `data-text-current-core.json`; the implementation hashes in `runtime-implementation.json` describe that historical handoff, when native and proposed module bytes matched. The selected receipt contains27 actual requests from32 original events, including discovery and four loaded-skill catalogs. Detailed ValueError traceback fields are omitted consistently from structured and JSON-encoded responses; native measurements and trace hashes are retained.

Publication review checks every regular/bold/italic/bold-italic font slot against the built-in-font profile, with unassigned style slots using the regular font fallback. Fresh typed native E2E tests create/read geometry and text, compare independent native fingerprints, save and reopen a relocated copy, and verify failure leaves datablocks and selection unchanged. The final source is based on updated public main and requires its own exact-head Blender4.5/5.2 native CI before merge. These tests provide no local native acceptance when `bpy` is unavailable.

## Publication validation

Fresh checks on Windows with Python 3.12.10 and Core/server 0.20.41 passed the repository-prescribed `vx just setup`, `check`, `prek` and `ci` recipes in an isolated task virtual environment. The final unit/contract lane passed 1,550 tests with 35 skips and two warnings; the coverage run also passed 20 subtests and reported 71% overall coverage. Lint, skill validation and the pre-commit format check passed, with 568 files unchanged by the formatter.

These results cover the updated public main and font validation fixes. Local `bpy` is unavailable, so they provide no native acceptance. The native CI for the PR's exact HEAD on Blender 4.5/5.2 is required before merge; the earlier 4.3 source qualification remains a separate historical snapshot.

Wheel/sdist builds and Twine metadata checks passed. All ten new Python files parse with Python 3.7 grammar. Artifact inspection compares packaged source with the final working tree, verifies LF bytes for the new capability files, and scans every payload and source-archive owner metadata for private host/workspace markers and credential patterns.

The first native run exposed three tests reading Core's reserved verification flag from `context`. The corrected tests assert top-level `postcondition.verified` and the native readback method for every successful text creation, preserving all formatting, font, transform, reopen and cleanup checks. The corrected commit `2c39bbb` passed ordinary CI and all eight supported-host native jobs: all 32 added cases ran with zero failures or skips. Runtime behavior and native skip conditions were unchanged.

Formal review identified a curve discovery schema that permitted two control points for a closed curve, while the runtime requires three. The schema now requires three points when `closed` is omitted (its default is true) or explicitly true; explicit false retains the two-point minimum. Regression checks compare the actual public schema and runtime validator across 2D/3D coordinates, closure modes, numeric bounds and point cardinality. Before integrating the portable-scene feature, the repository-prescribed `prek` lane passed 1,552 tests with 35 skips and the same two warnings. This metadata fix preserves runtime code and all 32 native cases and requires fresh exact-head CI before merge.

The small schema follow-up is based on combined public main `659b76d`, preserving both data geometry and portable scenes alongside MaterialX/USD. Its complete repository-prescribed `prek` lane passed 1,605 tests with 36 skips and the same two warnings. The final wheel/sdist must match this combined source, and supported-host CI must validate the follow-up's exact HEAD.
