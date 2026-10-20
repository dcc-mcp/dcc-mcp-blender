# Saved-scene render job acceptance

The separate `blender_render__start_saved_scene_job` entry point renders an
existing `.blend` in an owned worker without opening or saving the control
host's scene. It addresses the missing saved-file submission capability, not
an observed out-of-memory failure or a measured memory-performance claim.
Existing current-scene submission semantics are unchanged.

## Executed checks

- **107 focused unit/contract tests passed**: 44 saved-scene tests, 40 existing
  render-job tests and 23 render-skill tests. Native operations in those tests
  are doubles; real temporary symlinks/hardlinks test output/source alias
  rejection with unchanged source bytes and zero launches.
- Repository Ruff check/format and skill lint with warnings-as-errors passed.
- **Four real jobs** used Linux official Blender **4.5.13 LTS**, Core 0.20.46,
  the unchanged official bootstrap and the candidate source through real MCP
  discovery, skill registration and typed tools:
  1. An empty unsaved control host: completed, worker exit **0**.
  2. An unsaved sentinel control host: completed, worker exit **0**; filepath,
     dirty state, object location/custom property/selection, active object,
     frame, live JPEG format and camera were identical before and after.
  3. A separate header-only invalid `.blend`: failed, worker exit **1**; Blender
     reported **Missing DNA block**, and no image was written.
  4. Immediate cancellation of at most two tiny frames: cancelled, worker exit
     **-15**, with the original worker `Popen.wait()` confirmed.
- Both successful **64 × 64**, CPU, one-sample PNGs passed full pixel decoding:
  packed red `[255, 0, 0]` and external `//` green `[0, 255, 0]` resources resolved.
  Source hashes matched at submission, before load, after load and after render.
  The fixture's auto-run text marker remained absent. Actual worker arguments
  put `--disable-autoexec` before the source, followed by native load, the
  after-load check, render actions and final source verification.
- All four original worker processes were waited. The isolated host was frozen,
  terminated and waited; final owned identity/process-group checks found no live
  members. No production scene or installed adapter was changed.

The first native attempt created **zero fixtures and zero jobs**: HTTP initialize
succeeded while the registry was still booting, but an immediate `load_skill`
found no catalog entries. The executor incorrectly treated registration as
catalog readiness. The unchanged bootstrap calls `discover_skills()` after
`start()`, then flushes its `MCP_URL` marker. A bounded read-only `search_skills`
wait for the required names **and** that marker corrected the test precondition;
only then was `load_skill` called once. The second, separately approved attempt
passed the four jobs above. This was an executor readiness correction, not an
adapter installation/path change or a repeated mutation request.

## Small-fixture reproduction

Use one isolated host and a new, disposable absolute test directory. Through
the official bootstrap and MCP client:

1. Initialize; wait for the bootstrap marker and read-only catalog discovery of
   `blender-scene`, `blender-render` and `blender-scripting`. Load once and inspect
   the actual published `start_saved_scene_job` schema.
2. Use typed scene/render tools and `execute_script_file` for fixture setup.
   Create two size-1 planes at `(-0.5, 0, 0)` and `(0.5, 0, 0)`. Give each an
   image-texture-to-emission material: a packed 2 × 2 red image and an unpacked
   2 × 2 green PNG under `assets/relative.png`. Use an orthographic camera at
   `(0, 0, 3)`, scale 2.2, Standard view transform, black world, Cycles CPU,
   one sample, two threads, 64 × 64 PNG, no denoising/compositor/sequencer.
3. Save through `save_scene`, set the green image path to
   `//assets/relative.png`, and save again. Optionally include a harmless
   auto-run text that writes a marker only in this test directory. Compute the
   saved file's SHA-256 without modifying it.
4. Reset the control host to an empty unsaved scene. Submit the saved source
   through `start_saved_scene_job` with its absolute `source_filepath`, exact
   `expected_sha256`, absolute `output_pattern` ending in `frame_####`, explicit
   `output_format="PNG"`, frames 1–1, `resume_missing=false`,
   `factory_startup=true`, and `device="CPU"`. Poll the returned original job ID.
5. Require completed status, worker exit 0, all four source observations, and a
   fully decoded 64 × 64 PNG. Check pixels `(17, 32)` and `(47, 32)` for red and
   green. Compare control snapshots and verify no auto-run marker appeared.
   Repeat with an unsaved sentinel object and a different live JPEG format.
6. As separate jobs, submit a disposable file containing only `BLENDER-v450`
   with its own matching hash, then submit at most two valid tiny frames and
   immediately cancel. Require native invalid-load failure/no PNG. Claim running
   cancellation only if the worker actually exits by signal; if completion wins
   the race, report cancellation coverage as missing, without increasing load.
7. Wait every owned worker and the host. Retain original requests, responses,
   source receipts, stdout/stderr and process-exit evidence locally. Do not use
   stale registry entries or receipts as authority to terminate unrelated PIDs.

## Boundaries

This is **4.5.13-only small-fixture acceptance**, not a Blender 5.x/Windows/macOS
matrix or production-scale benchmark. The full installer suite and Python 3.7
interpreter gate were not run. Concurrent source mutation and boundary failures
are unit-tested, not represented as real native mutation tests.

Source hashes and output-alias checks are **point-in-time, non-atomic
observations**, not immutable snapshot isolation. The API hashes the `.blend`,
not external assets; their resolution was tested, but their integrity is not
guaranteed. `resume_missing` defaults false. Opt-in reuse follows existing
file-validity checks and does not bind old outputs to the source hash. Receipts
are diagnostics, not restarted-host job recovery or process ownership. This
change does not broaden generic resume, non-PNG validation or cancellation
lifecycle guarantees.
