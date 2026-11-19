"""Offline error-contract tests for native PCM mixdown readback.

No Blender / bpy / native encoder runs here. These tests drive the adapter's
pure readback helpers and the worker's fail-closed sample-count contract with
synthetic WAV bytes and mocked host modules. Native validation is intentionally
NOT_RUN in this suite; the measured native behaviour is recorded in
``docs/evidence/native-mixdown-upstream/``.
"""

from __future__ import annotations

import json
import struct
import sys
from types import SimpleNamespace

import pytest

from dcc_mcp_blender import _audio_export_ops as jobs
from dcc_mcp_blender import _audio_export_worker as worker
from dcc_mcp_blender import _audio_pcm_repair as repair
from dcc_mcp_blender._audio_export_worker import digest

# Windows NTSTATUS / exception codes as returned by subprocess (unsigned and
# their signed 32-bit reinterpretations). 0xC0000409 is the fast-fail code;
# 0xC0000005 is ACCESS_VIOLATION -- neither may be guessed as a native cause.
_WINDOWS_FAST_FAIL = 0xC0000409
_ACCESS_VIOLATION = 0xC0000005


def _signed32(unsigned):
    return unsigned - (1 << 32) if unsigned >= (1 << 31) else unsigned


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


def _stat_raising_path(exc):
    """A Path stand-in whose stat() always raises the given synthetic error."""

    class _Path:
        def __init__(self, *parts):
            pass

        def __truediv__(self, other):
            return self

        def stat(self):
            raise exc

    return _Path


def _duplicate_block_wav(expected_frames, accuracy, *, exact):
    """Minimal stereo S24 RIFF/WAVE with the predicted surplus frame count.

    ``exact`` controls whether the trailing PCM block is a byte-exact copy of
    the preceding final block. Both variants have the SAME surplus count, so
    only the strict byte-exact verifier can tell them apart.
    """
    alignment = 6  # 2 channels * 24-bit
    extra = expected_frames % accuracy or accuracy
    cut = expected_frames * alignment
    head = bytes((i * 7 + 13) % 256 for i in range(cut))
    final_block = head[cut - extra * alignment : cut]
    tail = final_block if exact else bytes(b ^ 0x5A for b in final_block)
    data = head + tail
    fmt = struct.pack("<HHIIHH", 1, 2, 48000, 48000 * alignment, alignment, 24)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


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
        assert contract["verdict"] == "NATIVE_SURPLUS_CANDIDATE"
        assert "DUPLICATE" not in contract["verdict"]  # count-only, not a duplicate claim
        assert contract["duplicate_block_confirmed"] is False
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
        corrected_frames=None,
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
        verified_samples = (
            _FakeSamples([[0.0, 0.0] for _ in range(corrected_frames)]) if corrected_frames is not None else None
        )
        state = {"decode_calls": 0}

        def sound_factory(path):
            # A successful strict correction re-decodes the second file; only
            # that path may return the shorter, sample-exact decoded prefix.
            if verified_samples is not None and str(path).endswith("audio-corrected.wav"):
                return SimpleNamespace(specs=(rate, 2), data=lambda: verified_samples)
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

    def test_worker_run_rejects_nonidentical_tail_without_truncation(self, tmp_path, monkeypatch):
        """Counterexample through the real worker: a matching surplus count with
        a non-byte-exact final block is still rejected by the strict verifier,
        and the original native WAV bytes are preserved (no unconditional trim).
        """
        blob = _duplicate_block_wav(2000, 240, exact=False)
        dest, _, _ = self._install(monkeypatch, tmp_path, 2080, frames=1, native_bytes=blob, opt_in=True)
        with pytest.raises(ValueError, match="Extra PCM bytes do not exactly duplicate"):
            worker.run(tmp_path)
        assert dest.read_bytes() == blob  # final bytes bound; never truncated
        assert not (tmp_path / "audio-corrected.wav").exists()
        assert not (tmp_path / "result.json").exists()

    def test_byte_exact_duplicate_is_confirmed_only_after_verification(self, tmp_path, monkeypatch):
        """Positive control: only a byte-exact duplicate promotes the candidate
        verdict to a confirmed duplicate block, and the original native WAV stays
        untouched while the opt-in second file is bound to the exact frame count.
        """
        expected_frames = 2000
        blob = _duplicate_block_wav(expected_frames, 240, exact=True)
        dest, _, _ = self._install(
            monkeypatch,
            tmp_path,
            2080,
            frames=1,
            native_bytes=blob,
            opt_in=True,
            corrected_frames=expected_frames,
        )
        worker.run(tmp_path)
        assert dest.read_bytes() == blob  # native artifact preserved, not truncated
        receipt = json.loads((tmp_path / "result.json").read_text())
        assert receipt["output_name"] == "audio-corrected.wav"
        assert receipt["correction"]["raw_pcm_duplicate_exact"] is True
        contract = receipt["sample_count_contract"]
        assert contract["verdict"] == "NATIVE_SURPLUS_CANDIDATE"
        assert contract["duplicate_block_confirmed"] is True
        assert receipt["frames"] == expected_frames


class TestReadbackNativeOutputStates:
    """Pure-helper controls: only a proven FileNotFoundError is 'missing'."""

    @pytest.mark.parametrize(
        "error_class",
        [PermissionError, OSError],
        ids=["permission", "generic_oserror"],
    )
    def test_unobservable_stat_failure_is_unknown_not_absent(self, monkeypatch, error_class):
        # Counterexample: a synthetic stat error must NOT be reported as an
        # observed missing / zero-byte artifact.
        monkeypatch.setattr(jobs, "Path", _stat_raising_path(error_class("denied")))
        readback = jobs._readback_native_output("ignored")
        assert readback["output_state"] == "unknown"
        assert readback["output_exists"] is None
        assert readback["output_bytes"] is None
        assert readback["output_error"] == error_class.__name__

    def test_proven_file_not_found_is_missing(self, monkeypatch):
        monkeypatch.setattr(jobs, "Path", _stat_raising_path(FileNotFoundError()))
        readback = jobs._readback_native_output("ignored")
        assert readback["output_state"] == "missing"
        assert readback["output_exists"] is False
        assert readback["output_bytes"] is None

    def test_zero_byte_is_zero_byte(self, tmp_path):
        (tmp_path / "audio.wav").write_bytes(b"")
        readback = jobs._readback_native_output(tmp_path)
        assert readback["output_state"] == "zero_byte"
        assert readback["output_exists"] is True
        assert readback["output_bytes"] == 0

    def test_nonzero_is_nonzero(self, tmp_path):
        (tmp_path / "audio.wav").write_bytes(b"RIFF" + bytes(44))
        readback = jobs._readback_native_output(tmp_path)
        assert readback["output_state"] == "nonzero"
        assert readback["output_exists"] is True
        assert readback["output_bytes"] == 48


class TestExitSignatureNtstatus:
    """Windows NTSTATUS codes are preserved neutrally, never guessed as fast-fail."""

    @pytest.mark.parametrize(
        "code, raw_hex",
        [
            (_ACCESS_VIOLATION, "0xC0000005"),
            (_WINDOWS_FAST_FAIL, "0xC0000409"),
            (_signed32(_ACCESS_VIOLATION), "0xC0000005"),
            (_signed32(_WINDOWS_FAST_FAIL), "0xC0000409"),
        ],
        ids=[
            "access_violation_unsigned",
            "fast_fail_unsigned",
            "access_violation_signed",
            "fast_fail_signed",
        ],
    )
    def test_windows_codes_are_neutral(self, code, raw_hex):
        sig = jobs._exit_signature(code)
        assert raw_hex in sig  # raw observed code is preserved
        assert "NTSTATUS" in sig
        assert "fast-fail" not in sig
        assert "abort" not in sig.lower()

    def test_posix_signal_is_not_ntstatus(self):
        sig = jobs._exit_signature(-6)
        assert "signal" in sig
        assert "NTSTATUS" not in sig
        assert "fast-fail" not in sig

    def test_plain_nonzero_exit(self):
        assert jobs._exit_signature(1) == "1 (nonzero)"

    def test_unconfirmed_exit(self):
        assert "unavailable" in jobs._exit_signature(None)

    def test_clean_exit(self):
        assert jobs._exit_signature(0) == "0 (clean)"


class TestDuplicateBlockCandidate:
    """Count agreement is only a candidate; byte-exact verification confirms."""

    def test_count_only_surplus_is_candidate_not_confirmed(self):
        contract = worker.native_sample_count_contract(2080, 2000, 240, True)
        assert contract["verdict"] == "NATIVE_SURPLUS_CANDIDATE"
        assert "DUPLICATE" not in contract["verdict"]  # no premature duplicate claim
        assert contract["duplicate_block_confirmed"] is False
        assert contract["predicted_native_surplus"] == 80
        assert contract["surplus"] == 80

    def test_same_surplus_nonidentical_block_rejected_by_strict_verifier(self):
        # The SAME surplus count, but the trailing block is not a byte-exact
        # duplicate -> the strict opt-in verifier must still reject it.
        blob = _duplicate_block_wav(2000, 240, exact=False)
        with pytest.raises(ValueError, match="Extra PCM bytes do not exactly duplicate"):
            repair.remove_verified_duplicate_final_block(blob, 2000, 240)

    def test_same_surplus_identical_block_confirmed_by_strict_verifier(self):
        # Positive control: only a byte-exact duplicate passes verification.
        blob = _duplicate_block_wav(2000, 240, exact=True)
        _, correction = repair.remove_verified_duplicate_final_block(blob, 2000, 240)
        assert correction["raw_pcm_duplicate_exact"] is True
        assert correction["removed_duplicate_frames"] == 80
