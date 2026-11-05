# Native Blender mixdown: PCM surplus and accuracy-dependent ffmpeg abort

Standalone, upstream-facing reproduction of the two remaining **native Blender**
`bpy.ops.sound.mixdown` defects reported after job isolation shipped. There is no
MCP, no `dcc-mcp-blender` import, no add-on, no external sound file and no
subjective/MP3 listening claim here. An empty scene mixes down to digital
silence of the requested inclusive frame length; both defects live in the native
PCM encoder, not in any source material or in the adapter.

## What is in this directory

| File | Purpose |
|---|---|
| `reproduce_native_mixdown.py` | Single-case Blender background reproducer (no MCP). Prints one JSON verdict. |
| `run_matrix.py` | Plain-CPython orchestrator: one Blender subprocess per case, aggregates results. |
| `results.json` | 58 measured cases, machine-readable. |
| `results.md` | Compact table of the same measurements. |
| `upstream-report-draft.md` | Ready-to-file Blender bug report, kept here as a draft (**not posted**). |

Related: [`docs/isolated-audio-export.md`](../../isolated-audio-export.md) documents the
owned-worker isolation shipped earlier; [`docs/native-audio-mixdown-guidance.md`](../../native-audio-mixdown-guidance.md)
documents the adapter-side fail-closed guidance.

## Reproduction

Windows (Blender 5.1.1 was used for the recorded measurements):

```bash
BLENDER="/c/Program Files/Blender Foundation/Blender 5.1/blender.exe"

"$BLENDER" --background --factory-startup \
  --python reproduce_native_mixdown.py -- \
  --out surplus.wav --frames 1-100 --accuracy 480 \
  --format S24 --channels STEREO --mixrate 48000 --fps 24 \
  --container WAV --codec PCM
```

Full matrix:

```bash
python run_matrix.py --blender "$BLENDER" \
  --script reproduce_native_mixdown.py --out-dir runs
```

A crash case aborts the child Blender before it can print the `RESULT_JSON_START`
marker; `run_matrix.py` records that as `0xC0000409` / `CRASH` with a zero-byte
output file. Running one subprocess per case is harness plumbing for
observation only — it is **not** a fix, not isolation, and not an audio-quality
claim.

## Findings

### 1. The FFMPEGWriter double-encode hypothesis is CONFIRMED

Source pinned to Blender 4.5.13 LTS commit
`daeeeca98fb0b6f0994b374d0069893186197a44`, file
`extern/audaspace/plugins/ffmpeg/FFMPEGWriter.cpp`:

- L438: `m_input_size = m_codecCtx->frame_size`. PCM codecs have `frame_size == 0`,
  so `write()` takes the `else // PCM data, can write directly!` branch (L536).
  Compressed codecs have a non-zero `frame_size` and take the buffered branch.
- L544–548 (PCM branch): sets `m_input_samples = length`, advances
  `m_position`, calls `encode()` — and **never resets `m_input_samples`**.
- L528–532 (compressed branch): calls `encode()` and then
  `m_input_samples = 0;` — so it does **not** double-encode.
- L466–470 (`~FFMPEGWriter`): `if(m_input_samples) encode();` — the destructor
  re-encodes the still-set count using the same `m_input_buffer`, whose contents
  are the final chunk (`encode()` uses `m_frame->nb_samples = m_input_samples`
  at L83 and `avcodec_fill_audio_frame(..., m_input_buffer.getSize(), 0)` at L94).

The consequence: the final `write()` chunk is emitted twice, byte-for-byte. This
is exactly the observed "surplus that repeats the preceding final block".

`source/blender/editors/sound/sound_ops.cc` L382–385 confirms the requested
length is inclusive: `AUD_mixdown(..., (end_frame - start_frame + 1) *
specs.rate / fps, accuracy, ...)`.

### 2. The surplus is fully predictable

For every successful WAV/PCM case measured:

```
requested = (end_frame - start_frame + 1) * rate / fps
surplus   = requested % accuracy,  or accuracy when requested % accuracy == 0
```

i.e. the size of the final `write()` chunk. All **30** SURPLUS cases in
`results.json` satisfy this law, and in every one the surplus bytes were an
**exact duplicate** of the preceding final block. This also explains the
earlier `+480` observations (where `requested % accuracy == 0`, so the final
full `accuracy` block is duplicated) and the accuracy-1024 observation (a
non-zero remainder). It matches the predictor already used by the adapter's
strict correction path (`_audio_pcm_repair.py`:
`extra = expected_frames % accuracy or accuracy`).

Three compressed-codec controls (FLAC) produced **EXACT** sample counts and no
abort, consistent with the buffered branch resetting `m_input_samples`.

### 3. The accuracy-dependent abort is reproduced

25 cases aborted natively with `0xC0000409` (MSVC fast-fail / `SIGABRT`
equivalent), zero-byte output, and no Python-level traceback. The reported
4.5.13 error is `aud::FileException: File couldn't be written, filling the
audio frame failed with ffmpeg.` — which maps to the `AUD_THROW` at
FFMPEGWriter.cpp L94 (`avcodec_fill_audio_frame`).

On the locally available Blender 5.1.1 (`b70da489d7f4`) the boundary measured
for WAV/PCM, 48 kHz stereo, fps 24 was:

- `accuracy == 1` aborted for every tested format (U8, S16, S24).
- For S24/S32/F32/F64, non-multiples of 32 (`40, 48, 100, 200, 240, 250, 400,
  1000, ...`) aborted; multiples of 32 (`32, 64, 96, 128, 160, 192, 224, 256,
  288, 320, 352, 480, 512, 800, 1024`) completed with the surplus above.
  U8/S16 tolerated non-multiples such as 200/240/480.
- `accuracy >= requested_samples` aborted regardless of format.
- The originating 4.5.13 crash configurations — frames `1–1` / accuracy `240` /
  S24, and accuracy `1` on a long VSE scene — both fall inside this measured
  bad region.

This boundary is **empirical and build-specific**; the internal root cause of
the abort is not established by this reproducer. A plausible mechanism is an
exception escaping `~FFMPEGWriter()` during the destructor's second `encode()`
call (an exception from a destructor terminates the process), but that is left
for upstream to confirm. Do not treat it as proven.

### 4. Version note

The hypothesis was verified against the exact 4.5.13 source commit named in
the issue. The empirical runs used the locally available **5.1.1** build, which
shows both defects are still present in a later major release — no claim is
made that any Blender version has fixed them.

## Bounds

- This is a **reproducer and source analysis**, not a fix. The native encoder
  is not repaired by anything here.
- No isolation is re-implemented; no subjective listening, MP3, or whole-case
  acceptance is claimed.
- Nothing in this directory silently truncates audio. The adapter's existing
  exact-check path remains the only supported correction.
- The upstream report is a **draft kept in-tree** and has not been published to
  any external tracker.
