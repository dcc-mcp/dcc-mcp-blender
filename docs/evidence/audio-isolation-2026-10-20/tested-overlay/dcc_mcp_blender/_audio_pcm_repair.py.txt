"""Strict opt-in correction of a proven duplicate final native PCM block."""

import struct


def remove_verified_duplicate_final_block(blob, expected_frames, accuracy):
    if type(expected_frames) is not int or expected_frames <= 0:
        raise ValueError("Positive integral expected sample-frame count required")
    if type(accuracy) is not int or accuracy <= 0:
        raise ValueError("Positive integral native mixdown accuracy required")
    if len(blob) < 12 or blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError("Only bounded RIFF WAVE is supported")
    if struct.unpack_from("<I", blob, 4)[0] + 8 != len(blob):
        raise ValueError("RIFF size mismatch; truncated/trailing bytes are not repairable")
    chunks = []
    offset = 12
    while offset < len(blob):
        if offset + 8 > len(blob):
            raise ValueError("Truncated chunk header")
        tag, size = struct.unpack_from("<4sI", blob, offset)
        end = offset + 8 + size
        if end + (size % 2) > len(blob):
            raise ValueError("Truncated chunk payload")
        if tag not in (b"fmt ", b"data", b"LIST", b"fact"):
            raise ValueError("Unsupported native output chunk; not a generic WAV repair")
        chunks.append((tag, blob[offset + 8 : end]))
        offset = end + (size % 2)
    for tag in (b"fmt ", b"data"):
        if sum(k == tag for k, v in chunks) != 1:
            raise ValueError("Exactly one fmt and data required")
    if sum(k == b"fact" for k, v in chunks) > 1:
        raise ValueError("Duplicate fact chunk")
    fmt = next(v for k, v in chunks if k == b"fmt ")
    if len(fmt) < 16:
        raise ValueError("Short format")
    code, channels, rate, byte_rate, alignment, bits = struct.unpack_from("<HHIIHH", fmt)
    if code in (1, 3) and not (len(fmt) == 16 or (len(fmt) == 18 and fmt[16:] == b"\0\0")):
        raise ValueError("Unexpected classic PCM format length or extension")
    if code == 65534:
        if len(fmt) != 40 or struct.unpack_from("<H", fmt, 16)[0] != 22:
            raise ValueError("Unsupported extensible format")
        valid_bits = struct.unpack_from("<H", fmt, 18)[0]
        if valid_bits != bits:
            raise ValueError("Unexpected valid-bit packing")
        guid = fmt[24:40]
        if guid[4:] != bytes.fromhex("00001000800000aa00389b71"):
            raise ValueError("Unknown format GUID")
        code = struct.unpack_from("<I", guid)[0]
    if channels != 2 or rate not in (44100, 48000) or (code, bits) not in ((1, 24), (3, 32)):
        raise ValueError("Only supported native stereo S24/F32 output can be corrected")
    if alignment != channels * bits // 8 or byte_rate != rate * alignment:
        raise ValueError("Invalid sample layout")
    data = next(v for k, v in chunks if k == b"data")
    if len(data) % alignment:
        raise ValueError("Partial sample frame")
    actual = len(data) // alignment
    extra = expected_frames % accuracy or accuracy
    if actual != expected_frames + extra or extra > expected_frames:
        raise ValueError("Output does not have exactly the predicted duplicated final block")
    cut = expected_frames * alignment
    if data[cut:] != data[cut - extra * alignment : cut]:
        raise ValueError("Extra PCM bytes do not exactly duplicate the preceding final block")
    rebuilt = []
    for tag, payload in chunks:
        if tag == b"data":
            payload = payload[:cut]
        if tag == b"fact":
            if len(payload) != 4 or struct.unpack("<I", payload)[0] not in (actual, expected_frames):
                raise ValueError("Unexpected fact metadata")
            payload = struct.pack("<I", expected_frames)
        rebuilt.append(tag + struct.pack("<I", len(payload)) + payload + b"\0" * (len(payload) % 2))
    body = b"WAVE" + b"".join(rebuilt)
    return b"RIFF" + struct.pack("<I", len(body)) + body, {
        "expected_frames": expected_frames,
        "native_frames": actual,
        "removed_duplicate_frames": extra,
        "raw_pcm_duplicate_exact": True,
        "unchanged_prefix_pcm": True,
        "sample_rate": rate,
        "channels": channels,
        "bits": bits,
    }
