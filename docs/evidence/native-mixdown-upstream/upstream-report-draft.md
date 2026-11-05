# Draft — Blender bug report (NOT FILED)

> This file is a tracked draft intended for a future upstream Blender report.
> It has **not** been submitted to any external issue tracker. Filing it is a
> separate, explicitly-authorized action. Keep the final report technical only.

**Title:** `sound.mixdown` (WAV/PCM) writes a duplicated final PCM block and can abort with "filling the audio frame failed with ffmpeg" depending on `accuracy`

**Component:** Audio / Audaspace (FFMPEG writer) + Video Sequencer mixdown operator
**Affected versions:** reproduced on 4.5.13 LTS (`daeeeca98fb0`) and 5.1.1 (`b70da489d7f4`), Windows 11 x64
**Severity:** wrong output on every PCM mixdown; hard process abort for certain parameters

## Summary

Two independent, reproducible defects in the native `bpy.ops.sound.mixdown`
operator when writing WAV/PCM:

1. Every successful PCM mixdown contains one extra block of samples at the end,
   and that block is a byte-for-byte duplicate of the preceding final block.
2. Certain `accuracy` / sample-format combinations abort the whole Blender
   process (0xC0000409 on Windows, `SIGABRT` equivalent), leaving a zero-byte
   output file.

Both are reproducible on an **empty scene** — no sound strips, no source files
are required, because the scene mixes down to silence of the requested length.

## Steps to reproduce

Save the reproducer script (a dependency-free, add-on-free Blender background
script) and run one case per invocation. For example:

```bash
blender --background --factory-startup --python reproduce_native_mixdown.py -- \
  --out surplus.wav --frames 1-100 --accuracy 480 \
  --format S24 --channels STEREO --mixrate 48000 --fps 24 \
  --container WAV --codec PCM
```

The script sets `scene.frame_start/frame_end`, `render.fps`, calls
`bpy.ops.sound.mixdown(...)`, then parses the resulting RIFF/WAVE `data` chunk
with the Python standard library to count decoded sample frames and compare the
trailing bytes with the preceding block. No external decoder is needed.

Minimal setup inside the script:

```python
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, 100
scene.render.fps = 24
scene.render.fps_base = 1.0
bpy.ops.sound.mixdown(
    filepath="surplus.wav", accuracy=480, container="WAV", codec="PCM",
    format="S24", channels="STEREO", mixrate=48000, check_existing=False)
```

## Observed vs expected

**Observed (defect 1 — surplus):**

| frames | accuracy | format | requested | decoded | surplus |
|---|---|---|---|---|---|
| 1-100 | 480 | S24 | 200000 | 200320 | 320 |
| 1-1 | 480 | S24 | 2000 | 2080 | 80 |
| 1-1 | 1024 | S24 | 2000 | 2976 | 976 |
| 1-1 | 200 | S16 | 2000 | 2200 | 200 |
| 1-100 | 480 | S16 | 200000 | 200320 | 320 |

In every case the extra trailing bytes are **exactly equal** to the
`surplus`-sized block immediately preceding them. The surplus equals the size
of the last chunk handed to the encoder: `requested % accuracy`, or `accuracy`
when `requested` is an exact multiple of `accuracy`.

**Expected:** decoded sample count equals
`(end_frame - start_frame + 1) * rate / fps`, with no duplicated trailing block.

**Observed (defect 2 — abort):**

| frames | accuracy | format | result |
|---|---|---|---|
| 1-1 | 240 | S24 | process abort, zero-byte output |
| 1-1 | 1 | U8 / S16 / S24 | process abort, zero-byte output |
| 1-100 | 240 | S24 | process abort, zero-byte output |
| 1-1 | 2000 (>= requested) | S24 | process abort, zero-byte output |

On 4.5.13 the reported error is:

```
aud::FileException: File couldn't be written, filling the audio frame failed with ffmpeg.
```

accompanied by exit `-6` / `SIGABRT`. On 5.1.1 the same parameter sets abort
with `0xC0000409` and no Python traceback. A compressed-codec control (FLAC)
with the same parameters completes with the exact requested sample count, which
isolates the problem to the PCM branch of the writer.

**Expected:** either a valid file of the requested length, or a clean operator
error without terminating the process.

## Suspected root cause (defect 1)

In `extern/audaspace/plugins/ffmpeg/FFMPEGWriter.cpp` at commit
`daeeeca98fb0b6f0994b374d0069893186197a44`:

- The constructor sets `m_input_size = m_codecCtx->frame_size` (L438). PCM
  codecs have `frame_size == 0`, compressed codecs do not.
- `FFMPEGWriter::write()` (L509) therefore splits into a buffered branch
  (L513) and a PCM branch (L536). The buffered branch resets the counter after
  encoding (L528–L532):

  ```cpp
  if(m_input_samples == m_input_size)
  {
      encode();
      m_input_samples = 0;
  }
  ```

  The PCM branch does not:

  ```cpp
  else // PCM data, can write directly!
  {
      m_input_buffer.assureSize(length * std::max(
          AUD_DEVICE_SAMPLE_SIZE(m_specs), samplesize));
      sample_t* buf = m_input_buffer.getBuffer();
      m_convert(..., length * m_specs.channels);
      m_input_samples = length;
      m_position += length;
      encode();
  }
  ```

- `~FFMPEGWriter()` (L466–L470) then runs:

  ```cpp
  if(m_input_samples)
      encode();
  ```

  Because the PCM branch left `m_input_samples` set to the final chunk length,
  the destructor calls `encode()` a second time on the same `m_input_buffer`,
  whose contents are still that final chunk (`encode()` sets
  `m_frame->nb_samples = m_input_samples` at L83 and fills the frame from
  `m_input_buffer` at L94). The final block is therefore written twice.

This also explains why FLAC/other compressed outputs are exact: their buffered
branch resets `m_input_samples` to zero.

`source/blender/editors/sound/sound_ops.cc` L382–385 confirms the inclusive
requested length: `AUD_mixdown(..., (end_frame - start_frame + 1) *
specs.rate / fps, accuracy, ...)`.

**Suggested direction:** reset `m_input_samples = 0` after `encode()` in the
PCM branch (mirroring the buffered branch), or have the destructor flush only
genuinely unwritten buffered data. Desirable as a separate check: raise a clean
operator error instead of allowing an exception to escape the destructor.

## Notes on defect 2

The abort boundary is parameter-dependent and build-specific. On 5.1.1 with
48 kHz stereo, fps 24, the measured bad region for 24/32-bit and float PCM
formats was `accuracy` values that are not multiples of 32, `accuracy == 1`,
and `accuracy >= requested_samples`. The internal root cause was not
established by this reproducer; one plausible mechanism is an exception thrown
from `encode()` inside `~FFMPEGWriter()` (an exception escaping a destructor
terminates the process), given `avcodec_fill_audio_frame` can fail with the
quoted message. Upstream confirmation is requested.

## Attachments / references

- `reproduce_native_mixdown.py` — single-case reproducer (standard library only).
- `run_matrix.py` — subprocess-per-case harness used for crash isolation during
  measurement. It is observation plumbing, not a proposed fix.
- `results.json` / `results.md` — 58 measured cases (30 surplus, 3 exact
  compressed controls, 25 aborts).

No third-party decoder, no audio quality/subjective listening claim, and no MP3
acceptance is involved in this report.
