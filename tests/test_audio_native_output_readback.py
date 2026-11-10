"""Offline error-contract tests for native PCM mixdown readback.

No Blender / bpy / native encoder runs here. These tests drive the adapter's
pure readback helpers and the worker's fail-closed sample-count contract with
synthetic WAV bytes and mocked host modules. Native validation is intentionally
NOT_RUN in this suite; the measured native behaviour is recorded in
``docs/evidence/native-mixdown-upstream/``.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from dcc_mcp_blender import _audio_export_ops as jobs
from dcc_mcp_blender import _audio_export_worker as worker
from dcc_mcp_blender._audio_export_worker import digest

# 0xC0000409 as returned by subprocess on Windows (unsigned 32-bit).
_WINDOWS_FAST_FAIL = 0xC0000409


class _FakeSamples(list):
    """Minimal stand-in for a decoded numpy array; unit CI has no numpy."""

    @property
    def ndim(self):
        return 2

    @property
    def shape(self):
        return (len(self), 2)


def _fake_numpy():
    """Only the numpy surface ``_audio_export_worker.run`` touches.

    The unit-test CI environment does not install numpy (it is a Blender runtime
    dependency), so it is injected into ``sys.modules`` for worker.run() calls,
    matching the existing pattern in test_audio_export_jobs.py.
    """
    return SimpleNamespace(
        isfinite=lambda samples: SimpleNamespace(all=lambda: True),
        array_equal=lambda left, right: list(left) == list(right),
        abs=lambda samples: SimpleNamespace(max=lambda: 0.0),
    )


def _fixture_job(tmp_path, code=0):
    for name in ("stdout.log", "stderr.log"):
        (tmp_path / name).write_text("native diagnostics")
    request = tmp_path / "request.json"
    request.write_text("{}")
    return {
        "job_id": "test",
        "status": "running",
        "process": SimpleNamespace(wait=lambda timeout: code, poll=lambda: code),
        "job_directory": str(tmp_path),
        "request_sha256": digest(request),
        "stdout_path": str(tmp_path / "stdout.log"),
        "stderr_path": str(tmp_path / "stderr.log"),
    }


class TestNativeOutputReadback:
    """Counterexamples: a crashed / zero-byte / missing native artifact is read back."""

    def test_zero_byte_native_abort_is_read_back(self, tmp_path):
        job = _fixture_job(tmp_path, _WINDOWS_FAST_FAIL)
        (tmp_path / "audio.wav").write_bytes(b"")
        jobs._watch(job, 1)
        assert job["status"] == "failed"
        assert job["returncode"] == _WINDOWS_FAST_FAIL
        assert job["exit_signature"].startswith("0xC0000409")
        assert job["native_output"] == {
            "output_name": "audio.wav",
            "output_exists": True,
            "output_bytes": 0,
            "output_state": "zero_byte",
        }
        persisted = json.loads((tmp_path / "status.json").read_text())
        assert persisted["native_output"]["output_state"] == "zero_byte"
        assert persisted["exit_signature"].startswith("0xC0000409")

    def test_missing_native_output_is_read_back(self, tmp_path):
        job = _fixture_job(tmp_path, -6)  # POSIX SIGABRT-shaped exit
        jobs._watch(job, 1)
        assert job["native_output"]["output_state"] == "missing"
        assert job["native_output"]["output_bytes"] is None
        assert "signal" in job["exit_signature"]

    def test_partial_nonzero_output_is_distinct_from_zero_byte(self, tmp_path):
        job = _fixture_job(tmp_path, 1)
        (tmp_path / "audio.wav").write_bytes(b"RIFF")  # truncated header only
        jobs._watch(job, 1)
        assert job["native_output"]["output_state"] == "nonzero"
        assert job["native_output"]["output_bytes"] == 4
        assert job["exit_signature"] == "1 (nonzero)"

    def test_completed_job_keeps_unchanged_contract(self, tmp_path):
        """Negative control: a valid export gains no error-readback keys."""
        job = _fixture_job(tmp_path)
        out = tmp_path / "audio.wav"
        out.write_bytes(b"a valid WAV payload")
        receipt = {
            "job_id": "test",
            "status": "completed",
            "full_decode": True,
            "request_sha256": job["request_sha256"],
            "output_sha256": digest(out),
            "output_name": "audio.wav",
        }
        (tmp_path / "result.json").write_text(json.dumps(receipt))
        jobs._watch(job, 1)
        assert job["status"] == "completed"
        assert "native_output" not in job
        assert "exit_signature" not in job


class TestExitSignature:
    """Negative controls for unaffected exit codes; classification only."""

    @pytest.mark.parametrize(
        "code, expected",
        [
            (None, "unavailable"),
            (0, "0 (clean)"),
            (-6, "signal"),
            (1, "1 (nonzero)"),
            (_WINDOWS_FAST_FAIL, "0xC0000409"),
        ],
    )
    def test_neutral_classification(self, code, expected):
        assert expected in jobs._exit_signature(code)


class TestSampleCountContract:
    """Pure, version-independent fail-closed contract; no truncation."""

    def test_exact_is_accepted_for_every_accuracy(self):
        # Negative controls: an exact output is unaffected by the accuracy value.
        for accuracy in (1, 32, 240, 480, 1024, 65536):
            assert worker.native_sample_count_contract(480, 480, accuracy, False) == {
                "verdict": "EXACT",
                "predicted_native_surplus": 0,
                "surplus": 0,
            }

    def test_measured_surplus_law_is_classified(self):
        # 480 % 240 == 0 -> predicted extra == accuracy == 240.
        contract = worker.native_sample_count_contract(720, 480, 240, True)
        assert contract["verdict"] == "NATIVE_DUPLICATE_FINAL_BLOCK_SURPLUS"
        assert contract["predicted_native_surplus"] == 240
        assert contract["surplus"] == 240

    def test_non_opted_in_surplus_fails_closed_and_names_the_law(self):
        with pytest.raises(ValueError) as exc:
            worker.native_sample_count_contract(720, 480, 240, False)
        message = str(exc.value)
        assert "not sample-exact" in message
        assert "predicted_native_surplus=240" in message
        assert "not truncated" in message
        assert "correct_duplicate_final_pcm_block" in message

    @pytest.mark.parametrize(
        "decoded, expected, verdict",
        [(479, 480, "SHORT_OUTPUT"), (481, 480, "UNEXPECTED_COUNT"), (725, 480, "UNEXPECTED_COUNT")],
    )
    def test_short_and_unexpected_counts_fail_closed(self, decoded, expected, verdict):
        with pytest.raises(ValueError, match="not sample-exact"):
            worker.native_sample_count_contract(decoded, expected, 240, False)
        assert worker.native_sample_count_contract(decoded, expected, 240, True)["verdict"] == verdict

    def test_invalid_accuracy_is_rejected_not_divided_by_zero(self):
        with pytest.raises(ValueError, match="Positive integral"):
            worker.native_sample_count_contract(720, 480, 0, True)


class TestWorkerIntegration:
    """Drive worker.run() with mocked bpy/aud and a numpy shim; no native Blender."""

    @staticmethod
    def _install(
        monkeypatch,
        tmp_path,
        decoded_frames,
        *,
        accuracy=240,
        opt_in=False,
        native_bytes=b"RIFF" + bytes(60),
        rate=48000,
        frames=24,
        fps=24,
    ):
        scene_path = tmp_path / "scene.blend"
        scene_path.write_bytes(b"fixture scene")
        dest = tmp_path / "audio.wav"

        def mixdown(**kwargs):
            if native_bytes is not None:
                dest.write_bytes(native_bytes)
            return {"FINISHED"}

        bpy = SimpleNamespace(
            ops=SimpleNamespace(
                wm=SimpleNamespace(open_mainfile=lambda **kw: {"FINISHED"}),
                sound=SimpleNamespace(mixdown=mixdown),
            ),
            data=SimpleNamespace(
                filepath=str(scene_path),
                sounds=[SimpleNamespace(library=None, packed_file=object(), filepath="")],
            ),
            context=SimpleNamespace(scene=SimpleNamespace(render=SimpleNamespace(fps=fps, fps_base=1.0))),
            path=SimpleNamespace(abspath=lambda p, **kw: p),
        )
        monkeypatch.setitem(sys.modules, "bpy", bpy)

        monkeypatch.setitem(sys.modules, "numpy", _fake_numpy())
        samples = _FakeSamples([[0.0, 0.0] for _ in range(decoded_frames)])
        fake_sound = SimpleNamespace(specs=(rate, 2), data=lambda: samples)
        state = {"decode_calls": 0}

        def sound_factory(path):
            state["decode_calls"] += 1
            return fake_sound

        monkeypatch.setitem(sys.modules, "aud", SimpleNamespace(Sound=sound_factory))
        request = {
            "job_id": "test",
            "scene_path": str(scene_path),
            "scene_sha256": digest(scene_path),
            "dependencies": [],
            "start_frame": 1,
            "end_frame": frames,
            "sample_rate": rate,
            "sample_format": "S24",
            "accuracy": accuracy,
            "correct_duplicate_final_pcm_block": opt_in,
        }
        (tmp_path / "request.json").write_text(json.dumps(request))
        return dest, native_bytes, state

    def test_zero_byte_output_fails_closed_before_decode(self, tmp_path, monkeypatch):
        dest, _, state = self._install(monkeypatch, tmp_path, 48240, native_bytes=b"")
        with pytest.raises(RuntimeError, match="zero-byte WAV output"):
            worker.run(tmp_path)
        assert state["decode_calls"] == 0
        assert dest.read_bytes() == b""
        assert not (tmp_path / "result.json").exists()

    def test_missing_output_fails_closed_before_decode(self, tmp_path, monkeypatch):
        _, _, state = self._install(monkeypatch, tmp_path, 48240, native_bytes=None)
        with pytest.raises(RuntimeError, match="no statable WAV output"):
            worker.run(tmp_path)
        assert state["decode_calls"] == 0
        assert not (tmp_path / "result.json").exists()

    def test_surplus_without_opt_in_fails_closed_without_truncation(self, tmp_path, monkeypatch):
        dest, native_bytes, _ = self._install(monkeypatch, tmp_path, 48240, opt_in=False)
        with pytest.raises(ValueError) as exc:
            worker.run(tmp_path)
        message = str(exc.value)
        assert "not sample-exact" in message
        assert "predicted_native_surplus=240" in message
        assert "not truncated" in message
        assert dest.read_bytes() == native_bytes  # never unconditionally truncated
        assert not (tmp_path / "audio-corrected.wav").exists()
        assert not (tmp_path / "result.json").exists()

    def test_opt_in_still_runs_strict_duplicate_verification(self, tmp_path, monkeypatch):
        """Negative control: the strict repair path is not bypassed by the new contract."""
        dest, native_bytes, _ = self._install(monkeypatch, tmp_path, 48240, opt_in=True)
        with pytest.raises(ValueError, match="Only bounded RIFF WAVE is supported"):
            worker.run(tmp_path)
        assert dest.read_bytes() == native_bytes
        assert not (tmp_path / "audio-corrected.wav").exists()

    def test_exact_output_is_unaffected_negative_control(self, tmp_path, monkeypatch):
        """Negative control: an exact export still succeeds with the EXACT contract."""
        dest, native_bytes, _ = self._install(monkeypatch, tmp_path, 48000, opt_in=False)
        worker.run(tmp_path)
        receipt = json.loads((tmp_path / "result.json").read_text())
        assert receipt["output_name"] == "audio.wav"
        assert receipt["sample_count_contract"]["verdict"] == "EXACT"
        assert receipt["correction"] is None
        assert dest.read_bytes() == native_bytes
