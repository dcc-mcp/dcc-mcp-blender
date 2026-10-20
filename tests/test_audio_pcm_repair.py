import struct
import unittest

from dcc_mcp_blender._audio_pcm_repair import remove_verified_duplicate_final_block as repair


def fixture(n=480, accuracy=240):
    fmt = struct.pack("<HHIIHH", 1, 2, 48000, 288000, 6, 24)
    data = bytes((i * 17 + 3) % 256 for i in range(n * 6))
    extra = n % accuracy or accuracy
    data += data[-extra * 6 :]
    body = b"WAVEfmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


class Repair(unittest.TestCase):
    def test_exact_prefix_not_fitted(self):
        b = fixture()
        out, r = repair(b, 480, 240)
        self.assertEqual(out[44:], b[44 : 44 + 480 * 6])
        self.assertEqual(r["removed_duplicate_frames"], 240)

    def test_all_matrix_shapes(self):
        for f in (1, 2, 100):
            for a in (480, 240):
                out, r = repair(fixture(f * 480, a), f * 480, a)
                self.assertEqual(len(out), 44 + f * 480 * 6)

    def test_extensible_float_with_fact(self):
        fmt = struct.pack("<HHIIHHHHI", 65534, 2, 48000, 384000, 8, 32, 22, 32, 3) + bytes.fromhex(
            "0300000000001000800000aa00389b71"
        )
        prefix = struct.pack("<" + "f" * 960, *[0.1] * (960))
        data = prefix + prefix[-240 * 8 :]
        chunks = (
            b"fmt "
            + struct.pack("<I", 40)
            + fmt
            + b"fact"
            + struct.pack("<II", 4, 720)
            + b"data"
            + struct.pack("<I", len(data))
            + data
        )
        blob = b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks
        out, r = repair(blob, 480, 240)
        self.assertEqual(r["bits"], 32)
        self.assertIn(b"fact" + struct.pack("<II", 4, 480), out)
        self.assertTrue(out.endswith(prefix))

    def test_nondublicate_nonzero_tail_rejected(self):
        b = bytearray(fixture())
        b[-1] ^= 1
        with self.assertRaises(ValueError):
            repair(bytes(b), 480, 240)

    def test_wrong_count_or_accuracy_rejected(self):
        for n, a in [(479, 240), (481, 240), (480, 480)]:
            with self.assertRaises(ValueError):
                repair(fixture(), n, a)

    def test_truncation_and_trailing_bytes_rejected(self):
        for b in (fixture()[:-1], fixture() + b"x"):
            with self.assertRaises(ValueError):
                repair(b, 480, 240)

    def test_invalid_format_rejected(self):
        b = bytearray(fixture())
        struct.pack_into("<H", b, 22, 1)
        with self.assertRaises(ValueError):
            repair(bytes(b), 480, 240)

    def test_no_repeated_repair(self):
        b, _ = repair(fixture(), 480, 240)
        with self.assertRaises(ValueError):
            repair(b, 480, 240)

    def test_duplicate_required_chunks_rejected(self):
        base = fixture()
        for chunk in (base[12:36], base[36:]):
            body = base[8:] + chunk
            invalid = b"RIFF" + struct.pack("<I", len(body)) + body
            with self.assertRaises(ValueError):
                repair(invalid, 480, 240)

    def test_classic_format_length_rejected(self):
        base = fixture()
        for extra in (b"x", b"\1\0", b"\0\0extra"):
            body = (
                base[8:16]
                + struct.pack("<I", 16 + len(extra))
                + base[20:36]
                + extra
                + b"\0" * (len(extra) % 2)
                + base[36:]
            )
            invalid = b"RIFF" + struct.pack("<I", len(body)) + body
            with self.assertRaises(ValueError):
                repair(invalid, 480, 240)

    def test_fact_count_and_length_rejected(self):
        base = fixture()
        for payload in (struct.pack("<I", 999), b"short", b""):
            chunk = b"fact" + struct.pack("<I", len(payload)) + payload + b"\0" * (len(payload) % 2)
            body = base[8:] + chunk
            with self.assertRaises(ValueError):
                repair(b"RIFF" + struct.pack("<I", len(body)) + body, 480, 240)

    def test_boolean_and_invalid_counts_rejected(self):
        for n, a in [(True, 240), (480, True), (0, 240), (-1, 240), (480, 0)]:
            with self.assertRaises(ValueError):
                repair(fixture(), n, a)


if __name__ == "__main__":
    unittest.main()
