"""Cross-check the duplicate-block predictor against measured native mixdown data.

The records in ``docs/evidence/native-mixdown-upstream/results.json`` come from
the standalone, add-on-free reproducer shipped in that directory. A change to
the predicted surplus formula should fail here instead of silently accepting a
WAV whose final block was duplicated by Blender's native PCM encoder.
"""

import json
import os
import struct
import unittest

from dcc_mcp_blender._audio_pcm_repair import remove_verified_duplicate_final_block as repair

_RESULTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "evidence",
    "native-mixdown-upstream",
    "results.json",
)


def _predicted_extra(requested_frames, accuracy):
    """Size of the final FFMPEGWriter::write() chunk, which is encoded twice."""
    return requested_frames % accuracy or accuracy


def _fixture(expected_frames, accuracy):
    """Build a stereo S24 RIFF/WAVE carrying the predicted duplicated final block."""
    fmt = struct.pack("<HHIIHH", 1, 2, 48000, 288000, 6, 24)
    data = bytes((i * 17 + 3) % 256 for i in range(expected_frames * 6))
    extra = _predicted_extra(expected_frames, accuracy)
    data += data[-extra * 6 :]
    body = b"WAVEfmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _load_cases():
    with open(_RESULTS_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)["cases"]


class NativeMixdownSurplusLaw(unittest.TestCase):
    def test_measured_surplus_matches_predictor(self):
        cases = [c for c in _load_cases() if c["verdict"] == "SURPLUS" and c["params"]["codec"] == "PCM"]
        self.assertGreaterEqual(len(cases), 20)
        for case in cases:
            predicted = _predicted_extra(case["requested_samples"], case["params"]["accuracy"])
            self.assertEqual(case["surplus_samples"], predicted, case["name"])
            self.assertIs(case["duplicate_final_block"], True, case["name"])

    def test_repair_removes_measured_surplus(self):
        cases = [
            c
            for c in _load_cases()
            if c["verdict"] == "SURPLUS" and c["params"]["codec"] == "PCM" and c["requested_samples"] <= 5000
        ]
        self.assertTrue(cases)
        for case in cases:
            expected = case["requested_samples"]
            accuracy = case["params"]["accuracy"]
            out, report = repair(_fixture(expected, accuracy), expected, accuracy)
            self.assertEqual(len(out), 44 + expected * 6, case["name"])
            self.assertEqual(report["removed_duplicate_frames"], _predicted_extra(expected, accuracy))
            self.assertIs(report["raw_pcm_duplicate_exact"], True)
            self.assertIs(report["unchanged_prefix_pcm"], True)

    def test_compressed_controls_are_exact(self):
        cases = [c for c in _load_cases() if c["verdict"] == "EXACT"]
        self.assertGreaterEqual(len(cases), 1)
        for case in cases:
            self.assertEqual(case["surplus_samples"], 0, case["name"])

    def test_crash_cases_have_no_decoded_output(self):
        cases = [c for c in _load_cases() if c["verdict"] == "CRASH"]
        self.assertGreaterEqual(len(cases), 10)
        for case in cases:
            self.assertIs(case["abnormal"], True, case["name"])
            self.assertIsNone(case["decoded_samples"], case["name"])


if __name__ == "__main__":
    unittest.main()
