# Bounded native scene-copy acceptance

The new typed operation saves a self-contained native copy into an explicitly authorized output root. It rejects overwrites, symlinks, reparse points and out-of-profile dependencies, stages a native save, runs a conservative path-form audit and publishes without clobbering an existing destination. Movie/sequence images, non-built-in fonts and sequence editors require a separate dependency audit. Script/IES nodes are rejected across material/world/light trees and node groups. It does not rewrite BLEND bytes or claim arbitrary-scene secret detection.

Native string setters can leave an old path suffix after a new shorter NUL-terminated value. The final implementation reads each field's bounded RNA capacity, fills it through the native setter with neutral ASCII, then assigns the intended relative value. Both render output and file-browser directory fields are covered. Unrecognized capacities fail closed. Logical original values are restored even when save, audit or cancellation fails.

The earlier whole-prefix-only audit was insufficient for that native padding. Its acceptance is superseded by the stronger final gate. Original failed artifacts and traces were retained, not silently replaced. Regression fixtures reproduce the stale tail, and the final guard recognizes the observed truncated form in addition to full path prefixes.

## Source qualification snapshot

- The complete default unit/contract lane passes1,519tests with34skips on Core/server0.20.41, including39focused portable-copy tests and22skill-structure checks. Native end-to-end/packaging lanes remain separate. The isolated test environment uses a real copied virtual-environment interpreter and scoped writable test storage
- Three actual source scenes were opened and copied through MCP: a1600×1000/512-sample hero, a1600×1000/512-sample orthogonal view and a1280×800/128-sample animation frame
- Each copied BLEND was relocated while both the original scene and clean source copy were unavailable. Native reopen preserved22 geometry objects,2 text objects, camera state and1,455 key values across5 animated objects. Each full-resolution native rerender has exactly equal decodedRGBA to its original reference
- Raw uncompressed BLEND task-path-fragment scans are clean; original source files were restored; the owned host stopped
- The accompanying JSON contains selected actual open/save/render requests and returned results, full trace hashes and validation summaries. Only absolute task workspace prefixes are replaced in the public excerpt

The actual source-qualification host is Blender4.3.2, using official adapter0.1.43-compatible integration plus recorded typed geometry/text and render helpers. At handoff, the native-tested portable implementation and the submitted source had equal parsed ASTs; only formatter line wrapping differed, and both byte hashes are recorded. The selected JSON and its hashes describe that historical snapshot. Publication review subsequently adds dependency guards for movie/sequence images and fonts, reparse-point rejection, and regression tests. These changes require fresh qualification on the final PR head.

The supported-host CI collects a native test that saves a typed copy, checks hash and state restoration, relocates it with original files unavailable, compares mesh/text/camera/keyframe state and verifies identical decoded render pixels. Its primary case has no skip path. A separate native browser-buffer case explicitly skips if the background host has not initialized its browser parameters; treat browser-specific clearing as natively qualified only after a supported host executes that case. Run supported Blender4.5+ native CI and platform publication checks before merge. No interactive Blender GUI acceptance or broad dependency sanitization is claimed.

## Publication validation

The post-handoff implementation was validated on public base `2075cec02d93f1cea4e0904a10d0a982c305106c`, using an isolated Windows Python 3.12.10 environment with Core/server 0.20.41.

- The repository's `check`, `prek` and coverage-enabled `ci` recipes each pass 1,570 tests with 35 skips and two existing schema-deprecation warnings. Ruff and SKILL lint pass; the final formatting gate leaves all 563 files unchanged.
- A separate focused run passes 75 tests: 11 native-buffer regression tests, 42 portable-copy contract tests and 22 skill-structure checks.
- All five new Python files pass the Python 3.7 syntax check. Wheel and source-distribution builds and `twine check` pass for version 0.2.13. Packaged source is compared against the reviewed files, and archive payloads and owner metadata are checked for local host/user/workspace markers.

The recipes run through existing `vx`/`just` tools with command-scoped PowerShell 7 and the isolated interpreter first in the child process path. The existing Windows `/dev/null` redirection fails before `prek`'s first pytest command; its defined full-suite fallback then executes successfully.

This local environment has no `bpy`, so these results provide unit, contract and packaging evidence. Supported Blender 4.5.13/5.2.1 native CI on the final PR head remains a merge requirement, with browser-specific acceptance reported only when its native case executes.
