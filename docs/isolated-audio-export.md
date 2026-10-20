# Isolated saved-snapshot audio export (experimental)

Related issue: https://github.com/dcc-mcp/dcc-mcp-blender/issues/320

This capability runs native Blender WAV mixdown in one owned worker, not the
interactive MCP host. It does not repair Blender's native crash. A failed worker
is terminal or explicitly termination-uncertain, not an invitation to retry.
Only one active/uncertain audio worker is allowed per adapter.

The caller explicitly supplies a saved scene path/hash and `use_saved_snapshot`.
Live edits are not saved or exported. External sound files must exactly match the
declared path/hash set; packed local sounds are bound by the scene hash. Linked
sound libraries are rejected in this first version. Auto-execution is disabled.

## Observed experiments, not a blanket platform guarantee

Official Blender 4.5.13 Linux x64, build `daeeeca98fb0`, adapter candidate based on
0.2.22, Core 0.20.46; all real runs used official MCP HTTP calls and fresh owned
bootstrap instances. No content-host installation was changed.

1. Native one-frame / accuracy 240 fixture aborted with exit -6 and an
   `aud::FileException` reporting failure to fill the audio frame. The MCP parent
   remained responsive to status/cancel/cleanup, then was explicitly terminated
   and waited. This is a real native crash, separate from the earlier injected
   abort test. The other accuracy-240 matrix cases were not run.
2. Two frames / accuracy 480 wrote 1,440 rather than 960 PCM frames. The 480-frame
   surplus exactly repeated the preceding raw PCM block. Explicit opt-in produced
   a separate corrected WAV, natively decoded it, and verified exact prefix
   equality. Independent reference NRMSE was 0.0000305658.
3. The existing 17-source Trail montage produced 1,373,280 native PCM frames.
   The same strict rule produced 1,372,800 frames (28.6 seconds), stereo 48 kHz,
   without changing the original WAV. Independent fixed-reference NRMSE was
   0.000001181867, peak 0.2262743, zero clipped samples; all seventeen first-256
   transient checks passed. The fade reference was derived beforehand from the
   matching native frame-volume interpolation, not fitted to the result.
   Difference against an ideal continuous fade is separately reported: 1.768866%.

Actual successful candidate wheel SHA256:
`fe494618af00e04925d7d99782a8c03224cc0aaeb7196a6d6c4143a1a4ee379d`.
The evidence folder retains exact candidate source hashes and sanitized actual
request/response records, original receipt hashes, original/corrected audio hashes,
quality measurements and process cleanup records. Sanitized records are reviewable
execution evidence, not an independently signed attestation. WAV assets are not
included in this adapter code PR. No subjective listening or MP3 acceptance is
claimed, and the full Showcase case remains unfinished.

Subsequent independent review strengthened linked-library rejection and cleanup
of unexpected wait errors; these changes have offline regression coverage. The
recorded real runs identify their exact earlier candidate, not an untested hash
of the final PR. The PCM algorithm and fixed sibling helper loader are unchanged.

## Narrow, explicit duplicate-block correction

Default behavior rejects every unexpected decoded sample count. With
`correct_duplicate_final_pcm_block: true`, correction requires a supported,
well-formed PCM RIFF/WAVE, the exact predicted last accuracy-block surplus and
byte-identical raw PCM duplication. It preserves `audio.wav`, exclusively creates
`audio-corrected.wav`, updates only validated container lengths, and compares the
full native decoded prefix sample-for-sample. Unexpected, malformed or differing
surpluses fail. This is not unconditional trimming and does not fix lost leading
transients. Independent content checks remain necessary.

The owned worker loads its fixed sibling helper by absolute `__file__` path,
without relying on Blender propagating package PYTHONPATH. The wheel was extracted
and checked with isolated Python, empty PYTHONPATH and unrelated working directory.
