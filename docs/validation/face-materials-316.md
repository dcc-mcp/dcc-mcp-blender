# Bounded per-face materials: acceptance evidence

This slice addresses [#316](https://github.com/dcc-mcp/dcc-mcp-blender/issues/316).
It does not claim complete material-authoring, GUI, gateway CLI or cross-platform
acceptance. The machine-readable summary is [face-materials-316.json](face-materials-316.json).

## Executed checks

- Full default suite: **2037 passed, 43 skipped**, no failures. This executor used
  a writable isolated HOME/XDG tree and exposed its dependency site-packages to
  the install-lifecycle tests' resolved-interpreter subprocesses. Initial runs
  without that environment hit read-only HOME and missing Core imports; those
  environmental failures were not suppressed or converted into skips.
- Focused contract suite: **107 passed**. Includes input/schema bounds, slot and
  same-count geometry revision changes, shared/read-only data, no partial invalid
  batches, safe repeats, and injected write/readback/rollback failures.
- Real **Blender 4.5.13 LTS / Python 3.11.15 / Core 0.20.46**, Linux background:
  **13 passed, zero skips**, including native save/reopen and GLB export/reimport.
  Fixtures in `tests/e2e/test_face_materials_e2e.py` use bpy explicitly; typed
  operations are under test. These direct native tests are not transport proof.
- A separately isolated wheel was bootstrapped using the unchanged official
  `blender_bootstrap.py`. Actual Streamable HTTP initialization, skill search/load,
  paginated `tools/list`, and **42 `tools/call` requests** succeeded as expected.
  The two new tools' live output schemas validated their actual success/error
  results, including Core-native `postcondition.verified`.
- Ruff check/format and skill metadata gates passed. A local Python 3.7
  grammar parse passed; the repository's actual Python 3.7 interpreter gate is
  left to CI (the local checker correctly refuses Python 3.12).

## Real transport workflow

A four-triangle mesh and three named materials were created using typed tools.
Slot assignment alone produced `[0, 0, 0, 0]`, reproducing the original gap.
`inspect_face_materials` supplied the required revision. Typed assignment of
face 1 to slot 1 and face 3 to slot 2 returned exact readback `[0, 1, 0, 2]`.
Repeating the batch returned `changed_count: 0` and `mutation_applied: false`.

Invalid batches (including a valid first record followed by an invalid record)
were rejected without changing the readback. Inspection pagination returned two
pages of two faces. Typed save, scene reset and reopen retained the assignments;
the old session revision was rejected. Typed GLB export produced three material
primitives, and typed import into a new scene retained the material face counts:
FaceRed 2, FaceBlue 1, FaceGold 1. Independent read-only geometric inspection
confirmed each triangle's material by its x-centroid, not export polygon order.

All geometry/material creation, slot and face assignment, save/open and
export/import mutations used typed `tools/call`. `execute_python` was used only
for read-only installed-module provenance and imported geometric association.
There was no script workaround for assigning polygon materials and no rendering.
The isolated test host was stopped and waited; the published adapter was not
modified. Raw transport requests/responses and the small blend/GLB artifacts
were retained alongside the execution report; artifact hashes are in the JSON.

## Reproduction

Run `pytest tests/test_face_material_contract.py` in the normal development
environment. Run `tests/e2e/test_face_materials_e2e.py` with pytest inside Blender,
using `-m e2e --override-ini=addopts=`; the repository's native CI runner also
collects it. For transport acceptance, bootstrap an isolated built wheel using
the official bootstrap, discover/load `blender-materials`, then call the tools
through actual MCP rather than importing their Python functions. Follow the
bounded workflow in the skill documentation; re-inspect after reopening files.
