# Native mixdown accuracy guidance (adapter-side, fail-closed)

This document is **guidance only**. It does not change runtime behavior, does
not fix Blender's native encoder, and does not replace the owned-worker
isolation described in [`docs/isolated-audio-export.md`](isolated-audio-export.md).
The measurements behind it are in
[`docs/evidence/native-mixdown-upstream/`](evidence/native-mixdown-upstream/).

## Standing rules

1. **Fail closed.** Unexpected decoded sample counts, malformed containers,
   zero-byte output, and worker aborts are terminal errors. Never retry a failed
   native mixdown silently and never treat a crashed worker as a transient.
2. **Never silently truncate.** The only supported correction is the existing
   strict `correct_duplicate_final_pcm_block` path, which keeps the original
   WAV, writes a second file, and requires exact predicted-surplus and
   byte-identical raw-PCM duplication plus full native decoded-prefix equality.
3. **Always decode and exact-check.** No caller should accept a native PCM
   mixdown as sample-exact just because the operator returned `FINISHED`.
4. **Do not claim the native encoder is fixed.** Isolation and correction are
   adapter-side containment, not an upstream fix. No MP3, subjective listening,
   or whole-case acceptance is claimed here.

## Why: two confirmed native defects

Blender's `bpy.ops.sound.mixdown` with WAV/PCM encodes the final `write()`
chunk twice. `FFMPEGWriter.cpp` (PCM branch) leaves `m_input_samples` set after
`encode()`, and `~FFMPEGWriter()` calls `encode()` again when that count is
non-zero. The resulting surplus is fully predictable:

```
requested = (end_frame - start_frame + 1) * rate / fps
surplus   = requested % accuracy,  or accuracy when requested % accuracy == 0
```

and the surplus is an exact duplicate of the preceding final block. This is the
same formula the adapter's `_audio_pcm_repair.remove_verified_duplicate_final_block`
already uses (`extra = expected_frames % accuracy or accuracy`), so the strict
correction path is consistent with the measured native behavior.

The second defect is a hard native abort (`0xC0000409` / `SIGABRT` equivalent)
for certain parameter combinations. In the recorded 58-case matrix each abort
left a zero-byte output file (`file_exists=true`, `output_bytes=0`,
`output_state=zero_byte` in `results.json`), with `crash_class`,
`exit_signature`, and `stdout_tail` / `stderr_tail` captured for attribution.

## Documented denylist (measured + extrapolated; not a guarantee)

Measured on Blender 5.1.1 (`b70da489d7f4`), Windows 11 x64, empty scene, WAV/PCM,
48 kHz stereo, fps 24. The same bad region contains the 4.5.13 crash
configurations reported earlier (frames `1–1` / accuracy `240` / S24, and
accuracy `1`).

| Condition | Observed | Recommendation |
|---|---|---|
| `accuracy == 1` | abort for U8, S16, S24 | **Deny.** |
| S24 with `accuracy % 32 != 0` (40, 48, 100, 200, 240, 250, 400, 1000) | abort | **Deny.** |
| S32 / F32 / F64 with `accuracy % 32 != 0` | abort at 240 only; other values not measured | **Deny (extrapolated).** |
| `accuracy >= requested_samples` | abort for S24 only; other formats not measured | **Deny (extrapolated).** |
| U8 / S16 with `accuracy` a non-multiple of 32 (200, 240, 480 tested) | completed with surplus, no abort | Allowed with exact-check, not trusted as exact. |
| `accuracy` a multiple of 32 and `< requested_samples` (32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 480, 512, 800, 1024) | completed with surplus, no abort | Allowed with exact-check, not trusted as exact. |
| FLAC / compressed codec controls | exact sample count, no abort | Still decode and verify; do not generalize to quality acceptance. |

**Measured vs extrapolated:** the S24 accuracy sweep and the
`accuracy >= requested_samples` S24 rows are directly measured. S32 / F32 / F64
were measured only at `accuracy=240` (abort) and `480` / `1024` (surplus); the
`accuracy >= requested_samples` row was measured only for S24. Rows marked
**(extrapolated)** are conservative inferences from the S24 behavior, **NOT**
observed results. They must not be presented as empirical evidence or filed
upstream as measured.

**Caveats:** this boundary is empirical and build-specific. It is a denylist of
*known-bad* settings, not a whitelist that certifies the remaining settings as
safe, and not a substitute for the fail-closed checks above. Different Blender
builds, sample rates, channel layouts, or codecs may shift it. The internal
root cause of the abort is unconfirmed.

## Runtime status

`_audio_export_ops.start_audio_export_job` still validates only
`1 <= accuracy <= 65536` (integral). **No runtime denylist or version gate was
added**, and this is deliberate rather than an oversight:

- The measured boundary comes from one locally available build (Blender 5.1.1,
  `b70da489d7f4`) on Windows, 48 kHz stereo, fps 24. The 4.5.13
  (`daeeeca98fb0`) evidence is source analysis plus two reported crash
  configurations, not a full re-measurement; CI targets 4.5.13 and 5.2.1.
- Several denylist rows are explicitly **extrapolated** (S32 / F32 / F64 and
  `accuracy >= requested_samples` for non-S24 formats), and the adapter accepts
  only S24 / F32 at 44.1 / 48 kHz, so several tabulated formats are not even
  reachable through this tool.
- A denylist is a list of *known-bad* settings, not a whitelist. Hard-coding it
  as a runtime guard would falsely block settings that may be fine on unmeasured
  builds and would imply every unblocked setting is safe. That would fabricate a
  safety guarantee the measurements do not support.

The denylist therefore remains **documentation only**. Extending it to runtime
protection would first need per-build measurements across the supported version
matrix. The adapter's protection is the version-independent fail-closed error
contract below, not a parameter blocklist.

That contract adds three pieces of readback, none of which fixes the native
encoder, blocks a parameter, or certifies a setting as safe:

- On any non-completed job the adapter stats the owned worker's native WAV and
  attaches `native_output` (`missing | zero_byte | nonzero | unknown`, plus
  `output_bytes`) and a neutral `exit_signature` that keeps the raw exit code
  without guessing a native cause. The first three states reuse the vocabulary
  of `docs/evidence/native-mixdown-upstream/results.json`; a `stat` failure
  that is not a proven `FileNotFoundError` stays `unknown` (existence/size not
  observed), never a fabricated absence.
- The worker rejects an absent or zero-byte native WAV before decoding, instead
  of surfacing an opaque decoder exception.
- A non-sample-exact PCM result without the strict opt-in correction now raises
  an attributable error naming the measured duplicate-final-block surplus law
  (`requested % accuracy or accuracy`) and fails closed **without truncating**.
  Matching that count is only a `NATIVE_SURPLUS_CANDIDATE` diagnosis; it does
  not claim a duplicate block. With `correct_duplicate_final_pcm_block=True` the
  existing byte-exact duplicate-block verification still runs unchanged, and
  only after it succeeds is `duplicate_block_confirmed` set to true.

## Operational checklist for a native PCM export

- Run in the owned worker, never in the interactive editor.
- Compute `requested` from the inclusive frame range before export.
- After export, decode the WAV with a bounded RIFF/WAVE reader and compare the
  sample count to `requested`.
- On `surplus == (requested % accuracy or accuracy)`, verify the trailing block
  is byte-identical to the preceding block and that the full decoded prefix is
  unchanged; only then may the opt-in corrected second file be produced.
- On any other count, malformed container, zero-byte output, or worker abort:
  fail closed, retain the original artifact and diagnostics, and report the
  failure. Do not trim to hide the surplus. The adapter's `native_output`
  readback now records whether the artifact was missing, zero-byte, nonzero,
  or unobservable (`unknown`).
