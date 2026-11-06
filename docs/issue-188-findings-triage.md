# Issue #188 findings triage

Triage of the five findings reported on
[dcc-mcp-blender#188](https://github.com/dcc-mcp/dcc-mcp-blender/issues/188)
("Round-up: 5 findings from an agent-driven modeling + lookdev run", observed
on adapter `0.1.37` / Blender 5.2.0). Mapping is against the current `main`
line (`0.2.26`). All five either are already fixed here or belong to
components outside this repository; **no code fix is outstanding in
`dcc-mcp-blender`**.

| # | Finding | Status | Owner / evidence |
|---|---|---|---|
| 1 | Installed marketplace skill not registered in the instance catalog until `reload-skills` | Out of repo | `dcc-mcp-cli` / `dcc-mcp-core` gateway skill management and on-demand loading (`dcc-mcp-gateway/.../skill_mgmt.rs`, `dcc-mcp-core/tests/test_on_demand_loading.py`). Not an adapter concern. |
| 2 | `lookdev_turntable__recommend_hdr_preset` annotated `execution: sync` but returns an async job | Out of repo | The tool lives in the `dcc-lookdev-turntable` marketplace skill, not in this repo; the `execution` annotation and async dispatch are core/CLI concerns. |
| 3 | `start_render_job`: `dcc-mcp-cli --wait` does not track the job; EXR-only output | Fixed here + remainder out of repo | EXR-only is **fixed** by [#195](https://github.com/dcc-mcp/dcc-mcp-blender/pull/195): `output_format` accepts `OPEN_EXR_MULTILAYER`, `OPEN_EXR`, `PNG`, `JPEG`, `TIFF`, `BMP`, and the scene's `render.image_settings.file_format` is reused when the option is omitted. `--wait` is a `dcc-mcp-cli` / core `jobs_get_status` mechanism; owned jobs are detached processes polled via `get_render_job`. |
| 4 | `dcc-mcp-cli load-skill --target-tool-slug` rejects the search `next_step` argument | Out of repo (likely fixed upstream) | `dcc-mcp-cli` flag parsing / core search (`capability_service.rs`). Current core `next_step.arguments` emits `tool_slug` or `skill_name` / `dcc` / `instance_id`, not `target_tool_slug`. |
| 5 | `lookdev_turntable__validate_stage` contract forces a two-phase turntable | Out of repo | The tool and its input schema (phase frame counts, `reference_anchor`, reference spheres) are defined in the `dcc-lookdev-turntable` marketplace skill. |

## What is already fixed in this repository

- `start_render_job` no longer hardcodes `OPEN_EXR_MULTILAYER`. `output_format`
  accepts display-ready containers (`PNG`, `JPEG`, `TIFF`, `BMP`) as well as
  both EXR variants, and the scene's saved `render.image_settings.file_format`
  is reused when the option is omitted. Output suffix and integrity checks are
  format-aware. See `src/dcc_mcp_blender/_render_job_ops.py`.
- `start_saved_scene_job` and `start_multiview_render_job` were added for
  saved-file and bounded-camera renders, also with an explicit `output_format`.

## Remaining DX gap documented here

`start_render_job` launches a detached Blender worker and returns a `job_id`
immediately. `dcc-mcp-cli --wait` polls the core `jobs_get_status` registry,
which cannot track these owned processes, so it returns before the render
finishes. The supported path is explicit polling with `get_render_job(job_id)`
(named in the tool's `next-tools` hint) and stopping through
`cancel_render_job(job_id)`. `blender-render/SKILL.md` now states this so an
agent does not wait on a job the CLI cannot observe; no separate EXR-to-PNG
view-transform conversion pass is needed before video encoding.

## Out-of-repo findings

Findings 1, 2, 4, 5 and the `--wait` portion of finding 3 belong to
`dcc-mcp-core` / `dcc-mcp-cli` and the `dcc-lookdev-turntable` marketplace
skill. They cannot be resolved by a change in this repository and should be
tracked in their owning components.
