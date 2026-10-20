# Verified save-scene contract

This bug was identified by code review during a showcase save audit, not an
observed production save failure or data-loss incident. Earlier successful
save/reopen acceptance remains valid. The existing `save_scene` ignored both
native save operators' return values and always returned success unless an
exception was raised. A previous file could therefore make a cancelled save
look successful to a caller that checked only file existence.

## Contract and compatibility

- Only the unambiguous native result `{"FINISHED"}` can succeed. `CANCELLED`,
  `RUNNING_MODAL`, mixed statuses and malformed results are rejected.
- The resulting Blender scene path must match the destination, and `stat` must
  show a nonempty regular file. Symlink/hardlink aliases and normalized spelling
  are compared by canonical path or filesystem identity, not raw strings.
- Save As resolves the requested destination before the operation changes the
  current scene path and passes an absolute path to Blender. Native testing
  established why this is needed: `save_as_mainfile` rejects Blender's `//`
  prefix and resolves ordinary relative paths using its own internal rules.
- The existing `context.filepath` field remains, now containing Blender's actual
  absolute saved path. `requested_filepath`, `file_size_bytes`, `operator_result`
  and Core-native `postcondition.verified` add explicit readback evidence.
- Verification proves these stated invariants only, not content integrity,
  durability against future disk failure, or a successful independent reopen.
  Save errors can have side effects, so attempted failures report
  `mutation_applied: null`, never claim rollback, and do not retry or delete files.
- Overwrite semantics remain those of the original save operation. No additional
  save, overwrite, backup, rollback or deletion operation was introduced.

## Executed evidence

See [save-scene-readback.json](save-scene-readback.json) for machine-readable
versions, wheel hash, counts and boundaries.

- Full default unit suite: **1975 passed, 43 skipped**, no failures. Ruff
  check/format and skill metadata checks passed.
- 45 focused fault-injection/contract tests and 13 existing scene unit tests
  passed. All filesystem fixtures are confined to temporary directories.
- Final native test run: **9 passed, zero skipped**, Linux Blender 4.5.13 LTS /
  Python 3.11.15 / Core 0.20.46. Covers Save As, Save current, changed-state
  reopen, ordinary and Blender-relative paths, extensionless paths, real
  directory/file symlinks, and a real invalid-destination failure.
- The first native run exposed four relative-path failures (five cases passed).
  That failure was retained, not treated as a skip. Passing the pre-resolved
  absolute destination corrected the discrepancy; all nine cases passed again.
- **12 actual typed MCP calls** used an isolated built wheel with the unchanged
  official bootstrap. Live schema/result validation passed. Typed Save As,
  another object creation, Save current, scene reset, open, and list readback
  proved both SavedMarker and AddedAfterSave were persisted. A real invalid
  destination returned failure with an unknown side-effect flag.
- Cancelled/mixed statuses and injected post-write failures are unit doubles,
  not represented as real Blender failures. Real native and MCP acceptance are
  separate evidence, not replaced by those doubles.

The isolated test process did not render, modify the shared content host, or
replace the published adapter installation. It was terminated and waited before
returning the temporary resource window. This PR does not change `open_scene`;
its separate return-value review is outside this minimal fix.
