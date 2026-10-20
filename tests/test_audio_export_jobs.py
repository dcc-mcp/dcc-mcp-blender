"""Offline lifecycle tests, not native Blender isolation acceptance."""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from dcc_mcp_blender import _audio_export_ops as jobs
from dcc_mcp_blender._audio_export_worker import digest


def fixture_job(tmp_path, code=0):
    for name in ["stdout.log", "stderr.log"]:
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


def test_native_abort_is_failed_with_diagnostics(tmp_path):
    job = fixture_job(tmp_path, -6)
    jobs._watch(job, 1)
    assert job["status"] == "failed" and job["returncode"] == -6
    assert job["stderr_tail"] == "native diagnostics"
    assert json.loads((tmp_path / "status.json").read_text())["status"] == "failed"


def test_zero_exit_without_validated_receipt_is_failed(tmp_path):
    job = fixture_job(tmp_path)
    (tmp_path / "audio.wav").write_bytes(b"RIFF")
    jobs._watch(job, 1)
    assert job["status"] == "failed"


def test_valid_receipt_requires_matching_output_hash(tmp_path):
    job = fixture_job(tmp_path)
    out = tmp_path / "audio.wav"
    out.write_bytes(b"unit test only")
    receipt = {
        "job_id": "test",
        "status": "completed",
        "full_decode": True,
        "request_sha256": job["request_sha256"],
        "output_sha256": digest(out),
    }
    (tmp_path / "result.json").write_text(json.dumps(receipt))
    jobs._watch(job, 1)
    assert job["status"] == "completed"
    job["status"] = "running"
    out.write_bytes(b"changed")
    jobs._watch(job, 1)
    assert job["status"] == "failed"


def test_timeout_stops_only_owned_process(tmp_path, monkeypatch):
    job = fixture_job(tmp_path)

    def timeout(**kwargs):
        raise subprocess.TimeoutExpired("worker", 1)

    job["process"].wait = timeout
    stopped = []
    monkeypatch.setattr(jobs, "_stop", lambda process: stopped.append(process))
    jobs._watch(job, 1)
    assert job["status"] == "timed_out" and stopped == [job["process"]]


def test_unknown_cancel_never_kills(monkeypatch):
    monkeypatch.setattr(jobs, "_stop", lambda p: pytest.fail("must not stop unknown job"))
    assert jobs.cancel_audio_export_job("missing")["success"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"accuracy": 0},
        {"accuracy": True},
        {"timeout_seconds": 0},
        {"sample_format": "MP3"},
        {"sample_rate": 96000},
        {"start_frame": 2, "end_frame": 1},
    ],
)
def test_invalid_submission_does_not_launch(tmp_path, monkeypatch, kwargs):
    monkeypatch.setitem(sys.modules, "bpy", SimpleNamespace())
    monkeypatch.setattr(jobs, "_launch_worker", lambda *a: pytest.fail("must not launch"))
    params = dict(job_directory=str(tmp_path / "new"), scene_sha256="0" * 64, start_frame=1, end_frame=24)
    params.update(kwargs)
    assert jobs.start_audio_export_job(**params)["success"] is False
    assert not (tmp_path / "new").exists()


def test_completed_output_change_fails_status(tmp_path):
    job = fixture_job(tmp_path)
    output = tmp_path / "audio.wav"
    output.write_bytes(b"original")
    job["status"] = "completed"
    job["validation"] = {"output_sha256": digest(output)}
    jobs._JOBS[job["job_id"]] = job
    try:
        output.write_bytes(b"changed")
        assert jobs.get_audio_export_job(job["job_id"])["context"]["status"] == "failed"
    finally:
        jobs._JOBS.pop(job["job_id"])


def test_missing_snapshot_opt_in_does_not_save_or_launch(tmp_path, monkeypatch):
    monkeypatch.setitem(
        sys.modules, "bpy", SimpleNamespace(data=SimpleNamespace(filepath="scene.blend", is_dirty=True))
    )
    monkeypatch.setattr(jobs, "_launch_worker", lambda *a: pytest.fail("must not launch"))
    result = jobs.start_audio_export_job(str(tmp_path / "new"), "0" * 64, 1, 24)
    assert result["success"] is False
    assert not (tmp_path / "new").exists()


@pytest.fixture
def clean_registry(monkeypatch):
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(jobs, "_SUBMITTING", False)


def valid_host(tmp_path, monkeypatch):
    source = tmp_path / "source.blend"
    source.write_bytes(b"fixture scene")
    bpy = SimpleNamespace(
        data=SimpleNamespace(
            filepath=str(source), is_dirty=False, sounds=[SimpleNamespace(name="packed", packed_file=object())]
        ),
        context=SimpleNamespace(scene=SimpleNamespace(render=SimpleNamespace(fps=24, fps_base=1))),
        app=SimpleNamespace(binary_path="blender"),
    )
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return source


@pytest.mark.parametrize("failure", ["persist", "thread"])
def test_post_launch_failure_reaps_worker(tmp_path, monkeypatch, clean_registry, failure):
    source = valid_host(tmp_path, monkeypatch)
    process = SimpleNamespace(pid=123, poll=lambda: -15)
    monkeypatch.setattr(jobs, "_launch_worker", lambda *args: process)
    stopped = []
    monkeypatch.setattr(jobs, "_stop", lambda p: stopped.append(p))
    if failure == "persist":
        original = jobs._persist

        def failing(job, strict=False):
            if strict:
                raise OSError("receipt unavailable")
            return original(job)

        monkeypatch.setattr(jobs, "_persist", failing)
    else:

        def fail_start():
            raise RuntimeError("thread unavailable")

        monkeypatch.setattr(jobs.threading, "Thread", lambda **kw: SimpleNamespace(start=fail_start))
    result = jobs.start_audio_export_job(
        str(tmp_path / "new"), digest(source), 1, 24, scene_path=str(source), use_saved_snapshot=True, input_files=[]
    )
    assert not result["success"] and stopped == [process]
    assert not jobs._SUBMITTING
    assert next(iter(jobs._JOBS.values()))["status"] == "failed"
    assert json.loads((tmp_path / "new/status.json").read_text())["status"] == "failed"


def test_active_or_pending_submission_refused(tmp_path, clean_registry):
    jobs._SUBMITTING = True
    assert not jobs.start_audio_export_job(str(tmp_path / "a"), "0" * 64, 1, 24)["success"]
    jobs._SUBMITTING = False
    jobs._JOBS["existing"] = {"status": "termination_uncertain"}
    assert not jobs.start_audio_export_job(str(tmp_path / "a"), "0" * 64, 1, 24)["success"]
    assert not (tmp_path / "a").exists()


def test_missing_logs_and_receipt_io_failure_keep_in_memory_failure(tmp_path, monkeypatch):
    job = fixture_job(tmp_path, -6)
    (tmp_path / "stderr.log").unlink()
    (tmp_path / "status.json").mkdir()  # Atomic replace cannot overwrite directory.
    jobs._watch(job, 1)
    assert job["status"] == "failed" and job["returncode"] == -6
    assert job["stderr_tail"].startswith("Log unavailable:")
    assert "receipt_write_error" in job


@pytest.mark.parametrize("operator_result,filepath", [({"CANCELLED"}, "source"), ({"FINISHED"}, "wrong")])
def test_worker_rejects_failed_or_wrong_scene_open(tmp_path, monkeypatch, operator_result, filepath):
    from dcc_mcp_blender import _audio_export_worker as worker

    source = tmp_path / "source.blend"
    source.write_bytes(b"scene")
    (tmp_path / "request.json").write_text(json.dumps({"scene_path": str(source), "scene_sha256": digest(source)}))
    monkeypatch.setitem(sys.modules, "aud", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "bpy",
        SimpleNamespace(
            ops=SimpleNamespace(wm=SimpleNamespace(open_mainfile=lambda **kw: operator_result)),
            data=SimpleNamespace(filepath=str(source if filepath == "source" else tmp_path / "wrong.blend")),
        ),
    )
    with pytest.raises(RuntimeError, match="exact saved source"):
        worker.run(tmp_path)


def test_request_digest_failure_happens_before_launch(tmp_path, monkeypatch, clean_registry):
    source = valid_host(tmp_path, monkeypatch)
    real_digest = jobs.digest

    def bad_digest(path):
        if str(path).endswith("request.json"):
            raise OSError("request unreadable")
        return real_digest(path)

    monkeypatch.setattr(jobs, "digest", bad_digest)
    monkeypatch.setattr(jobs, "_launch_worker", lambda *args: pytest.fail("must not launch"))
    assert not jobs.start_audio_export_job(
        str(tmp_path / "new"),
        real_digest(source),
        1,
        24,
        scene_path=str(source),
        use_saved_snapshot=True,
        input_files=[],
    )["success"]
    assert not jobs._SUBMITTING
    assert not jobs._JOBS


def test_uncertain_termination_blocks_new_job_and_allows_explicit_cancel(tmp_path, monkeypatch, clean_registry):
    job = fixture_job(tmp_path)
    job["status"] = "termination_uncertain"
    jobs._JOBS[job["job_id"]] = job
    stopped = []
    monkeypatch.setattr(jobs, "_stop", lambda process: stopped.append(process))
    assert not jobs.start_audio_export_job(str(tmp_path / "new"), "0" * 64, 1, 24)["success"]
    response = jobs.cancel_audio_export_job(job["job_id"])
    assert response["context"]["status"] == "cancelled" and stopped == [job["process"]]


def test_post_launch_stop_failure_retains_owned_slot(tmp_path, monkeypatch, clean_registry):
    source = valid_host(tmp_path, monkeypatch)
    process = SimpleNamespace(pid=123, poll=lambda: None)
    monkeypatch.setattr(jobs, "_launch_worker", lambda *args: process)

    def fail_stop(p):
        raise RuntimeError("wait uncertain")

    def fail_thread():
        raise RuntimeError("thread unavailable")

    monkeypatch.setattr(jobs, "_stop", fail_stop)
    monkeypatch.setattr(jobs.threading, "Thread", lambda **kw: SimpleNamespace(start=fail_thread))
    assert not jobs.start_audio_export_job(
        str(tmp_path / "new"), digest(source), 1, 24, scene_path=str(source), use_saved_snapshot=True, input_files=[]
    )["success"]
    assert next(iter(jobs._JOBS.values()))["status"] == "termination_uncertain"
    assert not jobs.start_audio_export_job(
        str(tmp_path / "other"), digest(source), 1, 24, scene_path=str(source), use_saved_snapshot=True, input_files=[]
    )["success"]
    assert not (tmp_path / "other").exists()


def test_explicit_saved_snapshot_does_not_save_or_export_dirty_live_scene(tmp_path, monkeypatch, clean_registry):
    source = valid_host(tmp_path, monkeypatch)
    sys.modules["bpy"].data.is_dirty = True
    sys.modules["bpy"].data.filepath = str(tmp_path / "different-live.blend")
    process = SimpleNamespace(pid=123, poll=lambda: None)
    monkeypatch.setattr(jobs, "_launch_worker", lambda *args: process)
    monkeypatch.setattr(jobs.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: None))
    result = jobs.start_audio_export_job(
        str(tmp_path / "new"), digest(source), 1, 24, scene_path=str(source), use_saved_snapshot=True, input_files=[]
    )
    assert result["success"]
    assert result["context"]["source_snapshot"]["path"] == str(source)
    assert "live edits" in result["context"]["warning"]
    request = json.loads((tmp_path / "new/request.json").read_text())
    assert request["scene_path"] == str(source) and request["dependencies"] == []


def test_conflicting_duplicate_input_hashes_refused(tmp_path, monkeypatch, clean_registry):
    source = valid_host(tmp_path, monkeypatch)
    audio = tmp_path / "tone.wav"
    audio.write_bytes(b"fixture")
    monkeypatch.setattr(jobs, "_launch_worker", lambda *a: pytest.fail("must not launch"))
    result = jobs.start_audio_export_job(
        str(tmp_path / "new"),
        digest(source),
        1,
        24,
        scene_path=str(source),
        use_saved_snapshot=True,
        input_files=[{"path": str(audio), "sha256": digest(audio)}, {"path": str(audio), "sha256": "0" * 64}],
    )
    assert not result["success"] and not (tmp_path / "new").exists()


def test_corrected_receipt_requires_opt_in_and_preserved_native(tmp_path):
    job = fixture_job(tmp_path)
    native = tmp_path / "audio.wav"
    corrected = tmp_path / "audio-corrected.wav"
    native.write_bytes(b"raw native output; unit only")
    corrected.write_bytes(b"corrected output; unit only")
    receipt = {
        "job_id": "test",
        "status": "completed",
        "full_decode": True,
        "request_sha256": job["request_sha256"],
        "output_name": corrected.name,
        "output_sha256": digest(corrected),
        "native_output_sha256": digest(native),
        "correction": {"raw_pcm_duplicate_exact": True},
    }
    (tmp_path / "result.json").write_text(json.dumps(receipt))
    jobs._watch(job, 1)
    assert job["status"] == "failed"
    job["correct_duplicate_final_pcm_block"] = True
    job["status"] = "running"
    jobs._watch(job, 1)
    assert job["status"] == "completed"
    jobs._JOBS[job["job_id"]] = job
    try:
        native.write_bytes(b"changed retained evidence")
        assert jobs.get_audio_export_job(job["job_id"])["context"]["status"] == "failed"
    finally:
        jobs._JOBS.pop(job["job_id"])


def test_receipt_cannot_escape_job_directory(tmp_path):
    job = fixture_job(tmp_path)
    with pytest.raises(ValueError):
        jobs._validated_output(job, {"output_name": "../audio.wav"})


def test_standalone_worker_loads_fixed_sibling_with_isolated_python(tmp_path):
    from pathlib import Path

    from dcc_mcp_blender import _audio_export_worker as worker

    package = Path(worker.__file__).parent
    for name in ("_audio_export_worker.py", "_audio_pcm_repair.py"):
        (tmp_path / name).write_bytes((package / name).read_bytes())
    code = (
        "import importlib.util; "
        f"s=importlib.util.spec_from_file_location('standalone_worker',{str(tmp_path / '_audio_export_worker.py')!r}); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "f=m._load_pcm_repair(); assert callable(f); "
        "print(f.__module__)"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": ""},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "_dcc_owned_audio_pcm_repair"


@pytest.mark.parametrize("packed", [None, object()])
def test_linked_sound_library_is_rejected(packed):
    from dcc_mcp_blender import _audio_export_worker as worker

    bpy = SimpleNamespace(data=SimpleNamespace(sounds=[SimpleNamespace(library=object(), packed_file=packed)]))
    with pytest.raises(ValueError, match="Linked sound libraries"):
        worker._sound_dependencies(bpy)


def test_local_packed_sound_is_bound_by_scene_hash():
    from dcc_mcp_blender import _audio_export_worker as worker

    bpy = SimpleNamespace(data=SimpleNamespace(sounds=[SimpleNamespace(library=None, packed_file=object())]))
    assert worker._sound_dependencies(bpy) == []


@pytest.mark.parametrize("cleanup_succeeds", [False, True])
def test_wait_exception_retains_slot_until_confirmed_exit(tmp_path, monkeypatch, cleanup_succeeds):
    job = fixture_job(tmp_path)
    state = {"code": None}

    def broken_wait(**kwargs):
        raise OSError("injected wait failure")

    def stop(process):
        if not cleanup_succeeds:
            raise OSError("injected termination failure")
        state["code"] = -15

    job["process"].wait = broken_wait
    job["process"].poll = lambda: state["code"]
    monkeypatch.setattr(jobs, "_stop", stop)
    jobs._watch(job, 1)
    assert job["status"] == ("failed" if cleanup_succeeds else "termination_uncertain")
    assert (job["status"] in jobs._ACTIVE) is (not cleanup_succeeds)
