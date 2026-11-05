# Native mixdown measurements

Blender **5.1.1** (`b70da489d7f4`), Windows 11 x64, empty scene, 48 kHz stereo, fps 24.

Cases: **58** total — 30 SURPLUS (exact duplicate of the final block), 3 EXACT (compressed-codec controls), 25 CRASH (0xC0000409 native abort, zero-byte output).

Requested samples = `(end_frame - start_frame + 1) * rate / fps`. Surplus = `requested % accuracy`, or `accuracy` when the remainder is zero.

| case | sweep | frames | accuracy | format | codec | requested | decoded | surplus | dup-final | exit | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `surplus_s24_100f_a480` | matrix | 1-100 | 480 | S24 | PCM | 200000 | 200320 | 320 | True | 0 | SURPLUS |
| `surplus_s24_1f_a480` | matrix | 1-1 | 480 | S24 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `surplus_s16_100f_a480` | matrix | 1-100 | 480 | S16 | PCM | 200000 | 200320 | 320 | True | 0 | SURPLUS |
| `surplus_s24_100f_a1024` | matrix | 1-100 | 1024 | S24 | PCM | 200000 | 200320 | 320 | True | 0 | SURPLUS |
| `surplus_s24_1f_a4096_gt_requested` | matrix | 1-1 | 4096 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `surplus_s24_1f_a2000_eq_requested` | matrix | 1-1 | 2000 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_a1` | matrix | 1-1 | 1 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_a64` | matrix | 1-1 | 64 | S24 | PCM | 2000 | 2016 | 16 | True | 0 | SURPLUS |
| `s24_1f_a240` | matrix | 1-1 | 240 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_a480` | matrix | 1-1 | 480 | S24 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `s24_1f_a1024` | matrix | 1-1 | 1024 | S24 | PCM | 2000 | 2976 | 976 | True | 0 | SURPLUS |
| `s24_1f_a2000` | matrix | 1-1 | 2000 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `fmt_U8_1f_a240` | matrix | 1-1 | 240 | U8 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `fmt_S16_1f_a240` | matrix | 1-1 | 240 | S16 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `fmt_S24_1f_a240` | matrix | 1-1 | 240 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `fmt_S32_1f_a240` | matrix | 1-1 | 240 | S32 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `fmt_F32_1f_a240` | matrix | 1-1 | 240 | F32 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `fmt_F64_1f_a240` | matrix | 1-1 | 240 | F64 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `control_flac_100f_a480` | matrix | 1-100 | 480 | S16 | FLAC | 200000 | 200000 | 0 | - | 0 | EXACT |
| `s24_1f_a2` | boundary | 1-1 | 2 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_a8` | boundary | 1-1 | 8 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_a16` | boundary | 1-1 | 16 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_a32` | boundary | 1-1 | 32 | S24 | PCM | 2000 | 2016 | 16 | True | 0 | SURPLUS |
| `s24_1f_a128` | boundary | 1-1 | 128 | S24 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `s24_1f_a160` | boundary | 1-1 | 160 | S24 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `s24_1f_a200` | boundary | 1-1 | 200 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_a256` | boundary | 1-1 | 256 | S24 | PCM | 2000 | 2208 | 208 | True | 0 | SURPLUS |
| `s24_1f_a320` | boundary | 1-1 | 320 | S24 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `s24_1f_a400` | boundary | 1-1 | 400 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_a512` | boundary | 1-1 | 512 | S24 | PCM | 2000 | 2464 | 464 | True | 0 | SURPLUS |
| `s24_1f_a800` | boundary | 1-1 | 800 | S24 | PCM | 2000 | 2400 | 400 | True | 0 | SURPLUS |
| `s24_100f_a1` | boundary | 1-100 | 1 | S24 | PCM | 200000 | - | - | - | 3221226505 | CRASH |
| `s24_100f_a240` | boundary | 1-100 | 240 | S24 | PCM | 200000 | - | - | - | 3221226505 | CRASH |
| `s24_10f_a240` | boundary | 1-10 | 240 | S24 | PCM | 20000 | - | - | - | 3221226505 | CRASH |
| `s16_1f_a1` | boundary | 1-1 | 1 | S16 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `f32_1f_a480` | boundary | 1-1 | 480 | F32 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `f32_1f_a1024` | boundary | 1-1 | 1024 | F32 | PCM | 2000 | 2976 | 976 | True | 0 | SURPLUS |
| `ctrl_flac_s24_a240` | boundary | 1-1 | 240 | S24 | FLAC | 2000 | 2000 | 0 | - | 0 | EXACT |
| `ctrl_flac_s16_a240` | boundary | 1-1 | 240 | S16 | FLAC | 2000 | 2000 | 0 | - | 0 | EXACT |
| `s24_1f_M32_96` | confirm | 1-1 | 96 | S24 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `s24_1f_M32_192` | confirm | 1-1 | 192 | S24 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `s24_1f_M32_224` | confirm | 1-1 | 224 | S24 | PCM | 2000 | 2208 | 208 | True | 0 | SURPLUS |
| `s24_1f_M32_288` | confirm | 1-1 | 288 | S24 | PCM | 2000 | 2272 | 272 | True | 0 | SURPLUS |
| `s24_1f_M32_352` | confirm | 1-1 | 352 | S24 | PCM | 2000 | 2240 | 240 | True | 0 | SURPLUS |
| `s24_1f_M32_2048` | confirm | 1-1 | 2048 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_N32_40` | confirm | 1-1 | 40 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_N32_48` | confirm | 1-1 | 48 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_N32_100` | confirm | 1-1 | 100 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_N32_250` | confirm | 1-1 | 250 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_1f_N32_1000` | confirm | 1-1 | 1000 | S24 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `S16_1f_a480` | confirm | 1-1 | 480 | S16 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `S32_1f_a480` | confirm | 1-1 | 480 | S32 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `F32_1f_a480` | confirm | 1-1 | 480 | F32 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `F64_1f_a480` | confirm | 1-1 | 480 | F64 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `U8_1f_a480` | confirm | 1-1 | 480 | U8 | PCM | 2000 | 2080 | 80 | True | 0 | SURPLUS |
| `s16_1f_a200` | confirm | 1-1 | 200 | S16 | PCM | 2000 | 2200 | 200 | True | 0 | SURPLUS |
| `u8_1f_a1` | confirm | 1-1 | 1 | U8 | PCM | 2000 | - | - | - | 3221226505 | CRASH |
| `s24_100f_a480` | confirm | 1-100 | 480 | S24 | PCM | 200000 | 200320 | 320 | True | 0 | SURPLUS |

Full machine-readable records: `results.json`.
