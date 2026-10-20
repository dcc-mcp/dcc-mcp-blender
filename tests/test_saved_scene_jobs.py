"""Saved-file submission contract; no Blender host or native workers required."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from dcc_mcp_blender import _render_job_ops as jobs
from dcc_mcp_blender import _saved_scene_source as source
from tests.conftest import load_and_call
from tests.test_skills_render import _assert_nullable_device_schema


class UntouchableScene:
    def __getattr__(self, name):
        raise AssertionError("Control scene was accessed: {}".format(name))


@pytest.fixture
def saved_job(monkeypatch, tmp_path):
    filepath = tmp_path / "saved source ' scene.blend"
    filepath.write_bytes(b"BLENDER-v450" + b"fixture; not a native Blender test")
    bpy = SimpleNamespace(
        app=SimpleNamespace(binary_path="blender"),
        data=UntouchableScene(),
        context=UntouchableScene(),
        ops=UntouchableScene(),
    )
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.setattr(jobs, "_JOBS", {})
    process = SimpleNamespace(pid=98765, returncode=None)
    process.poll = lambda: process.returncode
    launches = []

    def popen(command, **kwargs):
        launches.append((command, kwargs))
        return process

    monkeypatch.setattr(jobs.subprocess, "Popen", popen)
    params = dict(
        source_filepath=str(filepath),
        expected_sha256=hashlib.sha256(filepath.read_bytes()).hexdigest(),
        output_pattern=str(tmp_path / "renders" / "frame_####"),
        output_format="PNG",
        start_frame=1,
        end_frame=3,
    )
    return SimpleNamespace(params=params, source=filepath, launches=launches, process=process, bpy=bpy)


def test_saved_submission_never_reads_or_mutates_control_scene(saved_job):
    before = saved_job.source.read_bytes()
    result = jobs.start_saved_scene_job(**saved_job.params)
    assert result["success"] is True
    context = result["context"]
    assert context["kind"] == "saved_scene"
    assert context["source_filepath"] == str(saved_job.source)
    assert context["source_sha256"] == saved_job.params["expected_sha256"]
    assert context["source_size_bytes"] == len(before)
    assert context["output_format"] == "PNG"
    assert context["device"] is None
    assert context["resume_missing"] is False
    assert saved_job.source.read_bytes() == before
    assert jobs._JOBS[context["job_id"]]["process"] is saved_job.process
    command, kwargs = saved_job.launches[0]
    source_index = command.index(str(saved_job.source))
    assert command[:4] == ["blender", "--background", "--factory-startup", "--disable-autoexec"]
    assert command.index("--disable-autoexec") < source_index
    assert command.index("--python-exit-code") < source_index
    assert "before_load" in command[source_index - 1]
    assert command[source_index + 1] == "--python-expr"
    assert "after_load" in command[source_index + 2]
    assert command[-2] == "--python-expr"
    assert "after_render" in command[-1]
    assert "--cycles-device" not in command
    assert [command[i + 1] for i, value in enumerate(command) if value == "--render-frame"] == ["1", "2", "3"]
    assert kwargs["env"]["DCC_MCP_BACKGROUND_RENDER"] == "1"
    assert kwargs["cwd"] == str(saved_job.source.parent / "renders")
    assert kwargs.get("start_new_session") or kwargs.get("creationflags")
    receipt = json.loads(Path(context["source_receipt_path"]).read_text())
    assert receipt["job_id"] == context["job_id"]
    assert receipt["launch_settings"]["output_format"] == "PNG"
    assert receipt["launch_settings"]["disable_autoexec"] is True


def test_live_unsaved_sentinel_is_preserved(saved_job):
    saved_job.bpy.data = SimpleNamespace(filepath="", is_dirty=True, objects=["unsaved sentinel"])
    saved_job.bpy.context = SimpleNamespace(
        scene=SimpleNamespace(render=SimpleNamespace(image_settings=SimpleNamespace(file_format="FFMPEG")))
    )
    state = repr(saved_job.bpy)
    result = load_and_call("blender-render/scripts/start_saved_scene_job.py", saved_job.bpy, **saved_job.params)
    assert result["success"]
    assert repr(saved_job.bpy) == state


@pytest.mark.parametrize(
    "changes",
    [
        {"source_filepath": "relative.blend"},
        {"expected_sha256": "not-a-hash"},
        {"expected_sha256": "0" * 64},
        {"output_format": None},
        {"output_format": ""},
        {"output_format": "FFMPEG"},
        {"start_frame": 4},
        {"start_frame": -1},
        {"start_frame": True},
        {"end_frame": 1048575},
        {"end_frame": 2.5},
        {"step": 0},
        {"step": True},
        {"device": "BOGUS"},
        {"device": ""},
        {"resume_missing": 1},
        {"factory_startup": "yes"},
        {"output_pattern": "relative_####"},
        {"output_pattern": "/tmp/missing-placeholder"},
    ],
)
def test_invalid_requests_do_not_launch(saved_job, changes):
    result = jobs.start_saved_scene_job(**dict(saved_job.params, **changes))
    assert result["success"] is False
    assert not saved_job.launches
    assert not jobs._JOBS


@pytest.mark.parametrize("kind", ["missing", "invalid", "directory", "wrong_suffix"])
def test_bad_sources_do_not_launch(saved_job, kind):
    if kind == "missing":
        saved_job.source.unlink()
    elif kind == "directory":
        saved_job.source.unlink()
        saved_job.source.mkdir()
    elif kind == "wrong_suffix":
        saved_job.params["source_filepath"] = str(saved_job.source.with_suffix(".txt"))
    else:
        saved_job.source.write_bytes(b"not a Blender file")
        saved_job.params["expected_sha256"] = hashlib.sha256(saved_job.source.read_bytes()).hexdigest()
    assert not jobs.start_saved_scene_job(**saved_job.params)["success"]
    assert not saved_job.launches


def test_device_override_and_autoexec_without_factory_startup(saved_job):
    result = jobs.start_saved_scene_job(**saved_job.params, device="CPU", factory_startup=False)
    command = saved_job.launches[0][0]
    assert result["success"]
    assert "--factory-startup" not in command
    assert command.index("--disable-autoexec") < command.index(str(saved_job.source))
    assert command[-3:] == ["--", "--cycles-device", "CPU"]
    assert "after_render" in command[-4]


def test_source_guard_detects_change_before_load_and_keeps_job_identity(saved_job):
    result = jobs.start_saved_scene_job(**saved_job.params)
    context = result["context"]
    command = saved_job.launches[0][0]
    saved_job.source.write_bytes(saved_job.source.read_bytes() + b"changed after submission")
    with pytest.raises(ValueError, match="fingerprint mismatch at before_load"):
        exec(command[command.index("--python-expr") + 1], {})
    saved_job.process.returncode = 1
    status = jobs.get_render_job(context["job_id"])["context"]
    assert status["job_id"] == context["job_id"]
    assert status["status"] == "failed"
    assert "fingerprint mismatch" in status["error"]
    assert status["source_receipt"]["phase"] == "failed"
    assert "before_load" in status["source_receipt"]["observations"]
    assert jobs.get_render_job(context["job_id"])["context"]["return_code"] == 1


def _check_phase(context, phase):
    source.check_source(
        context["source_receipt_path"],
        context["job_id"],
        context["source_filepath"],
        context["source_sha256"],
        context["source_size_bytes"],
        phase,
    )


@pytest.mark.parametrize("phase", ["after_load", "after_render"])
def test_source_guard_detects_late_change(saved_job, phase):
    context = jobs.start_saved_scene_job(**saved_job.params)["context"]
    _check_phase(context, "before_load")
    saved_job.source.write_bytes(saved_job.source.read_bytes() + b"late change")
    with pytest.raises(ValueError, match="fingerprint mismatch at " + phase):
        _check_phase(context, phase)


def test_failed_native_load_cannot_render_startup_scene(saved_job):
    context = jobs.start_saved_scene_job(**saved_job.params)["context"]
    saved_job.bpy.data = SimpleNamespace(filepath="")
    with pytest.raises(ValueError, match="did not load the requested"):
        _check_phase(context, "after_load")


def test_success_requires_final_source_receipt_and_valid_frames(saved_job):
    context = jobs.start_saved_scene_job(**saved_job.params)["context"]
    _check_phase(context, "before_load")
    saved_job.bpy.data = SimpleNamespace(filepath=str(saved_job.source))
    _check_phase(context, "after_load")
    _check_phase(context, "after_render")
    png = (Path(__file__).parent / "fixtures" / "png" / "basn6a08.png").read_bytes()
    for frame in (1, 2, 3):
        jobs._expected_output_path(saved_job.params["output_pattern"], frame, output_format="PNG").write_bytes(png)
    saved_job.process.returncode = 0
    status = jobs.get_render_job(context["job_id"])["context"]
    assert status["status"] == "completed"
    assert status["written_frame_count"] == 3
    assert set(status["source_receipt"]["observations"]) == {"submission", "before_load", "after_load", "after_render"}
    assert status["return_code"] == 0


def test_exit_zero_is_not_enough_without_final_source_check(saved_job):
    context = jobs.start_saved_scene_job(**saved_job.params, resume_missing=True)["context"]
    png = (Path(__file__).parent / "fixtures" / "png" / "basn6a08.png").read_bytes()
    for frame in (1, 2, 3):
        jobs._expected_output_path(saved_job.params["output_pattern"], frame, output_format="PNG").write_bytes(png)
    saved_job.process.returncode = 0
    status = jobs.get_render_job(context["job_id"])["context"]
    assert status["status"] == "failed"
    assert "did not finish" in status["error"]


def test_cancel_uses_existing_owned_handle_not_receipt_pid(saved_job, monkeypatch):
    context = jobs.start_saved_scene_job(**saved_job.params)["context"]
    terminated = []
    monkeypatch.setattr(jobs, "_terminate_process_tree", lambda process: terminated.append(process))
    receipt = source.read_source_receipt(context["source_receipt_path"], context["job_id"])
    receipt["pid"] = 1234
    source.write_source_receipt(context["source_receipt_path"], receipt)
    for _ in range(2):
        assert jobs.cancel_render_job(context["job_id"])["context"]["status"] == "cancelled"
    assert terminated == [saved_job.process]


def test_launch_failure_retains_original_id_and_diagnostics(saved_job, monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("fixture launch failure")

    monkeypatch.setattr(jobs, "_launch_worker", fail)
    result = jobs.start_saved_scene_job(**saved_job.params)
    assert not result["success"]
    context = result["context"]
    status = jobs.get_render_job(context["job_id"])["context"]
    assert status["status"] == "failed"
    assert "fixture launch failure" in status["error"]
    assert Path(status["source_receipt_path"]).is_file()


def test_symlink_source_path_is_not_relocated(saved_job):
    link = saved_job.source.parent / "linked.blend"
    try:
        link.symlink_to(saved_job.source)
    except OSError:
        pytest.skip("symlinks unavailable")
    result = jobs.start_saved_scene_job(**dict(saved_job.params, source_filepath=str(link)))
    assert result["success"]
    assert result["context"]["source_filepath"] == str(link)
    assert str(link) in saved_job.launches[0][0]
    assert str(saved_job.source) not in saved_job.launches[0][0]


def test_gzip_source_hashes_original_bytes(saved_job):
    payload = gzip.compress(saved_job.source.read_bytes())
    saved_job.source.write_bytes(payload)
    assert source.source_fingerprint(saved_job.source)["sha256"] == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_output_alias_is_rejected_before_launch_without_source_damage(saved_job, link_kind):
    output = jobs._expected_output_path(saved_job.params["output_pattern"], 2, output_format="PNG")
    output.parent.mkdir()
    before = saved_job.source.read_bytes()
    try:
        if link_kind == "symlink":
            output.symlink_to(saved_job.source)
        else:
            os.link(str(saved_job.source), str(output))
    except OSError:
        pytest.skip("{} unavailable".format(link_kind))
    result = jobs.start_saved_scene_job(**saved_job.params)
    assert not result["success"]
    assert "aliases the saved source" in str(result)
    assert not saved_job.launches
    assert not jobs._JOBS
    assert saved_job.source.read_bytes() == before


@pytest.mark.parametrize("phase", ["before_load", "after_load"])
def test_worker_rechecks_new_output_alias_before_render(saved_job, phase):
    context = jobs.start_saved_scene_job(**saved_job.params)["context"]
    before = saved_job.source.read_bytes()
    output = jobs._expected_output_path(saved_job.params["output_pattern"], 3, output_format="PNG")
    try:
        os.link(str(saved_job.source), str(output))
    except OSError:
        pytest.skip("hardlinks unavailable")
    with pytest.raises(ValueError, match="aliases the saved source"):
        _check_phase(context, phase)
    assert saved_job.source.read_bytes() == before
    assert source.read_source_receipt(context["source_receipt_path"], context["job_id"])["phase"] == "failed"


def test_change_during_submission_hash_fails_before_launch(saved_job, monkeypatch):
    original = hashlib.sha256

    class ChangingDigest:
        def __init__(self):
            self.digest = original()

        def update(self, payload):
            self.digest.update(payload)
            with saved_job.source.open("ab") as stream:
                stream.write(b"changed during hashing")

        def hexdigest(self):
            return self.digest.hexdigest()

    # One write is sufficient; repeatedly extending an input would never EOF.
    digest = ChangingDigest()
    first_update = digest.update

    def update_once(payload):
        digest.update = digest.digest.update
        first_update(payload)

    digest.update = update_once
    monkeypatch.setattr(source.hashlib, "sha256", lambda: digest)
    result = jobs.start_saved_scene_job(**saved_job.params)
    assert not result["success"]
    assert "changed while hashing" in str(result)
    assert not saved_job.launches


def test_opt_in_resume_reports_no_worker_and_no_source_provenance(saved_job):
    png = (Path(__file__).parent / "fixtures" / "png" / "basn6a08.png").read_bytes()
    Path(saved_job.params["output_pattern"]).parent.mkdir()
    for frame in (1, 2, 3):
        jobs._expected_output_path(saved_job.params["output_pattern"], frame, output_format="PNG").write_bytes(png)
    result = jobs.start_saved_scene_job(**saved_job.params, resume_missing=True)
    assert result["success"]
    assert not saved_job.launches
    assert "no worker ran" in result["message"]
    assert result["context"]["source_receipt"]["phase"] == "not_run"
    assert result["context"]["expected_frame_count"] == 0
    assert result["context"]["return_code"] is None


def test_saved_device_error_recommends_same_entry_point(saved_job):
    context = jobs.start_saved_scene_job(**saved_job.params, device="OPTIX")["context"]
    Path(context["stderr_path"]).write_text("Found no Cycles device of the specified type")
    saved_job.process.returncode = 1
    status = jobs.get_render_job(context["job_id"])["context"]
    assert "start_saved_scene_job" in status["failure_hint"]
    assert "Retry start_render_job" not in status["failure_hint"]


def test_saved_tool_schema_requires_explicit_source_and_format():
    path = Path("src/dcc_mcp_blender/skills/blender-render/tools.yaml")
    tool = next(item for item in yaml.safe_load(path.read_text())["tools"] if item["name"] == "start_saved_scene_job")
    schema = tool["input_schema"]
    assert set(schema["required"]) == {
        "source_filepath",
        "expected_sha256",
        "output_pattern",
        "output_format",
        "start_frame",
        "end_frame",
    }
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["output_format"]["enum"]) == set(jobs._OUTPUT_FORMATS)
    assert schema["properties"]["resume_missing"]["default"] is False
    assert schema["properties"]["factory_startup"]["default"] is True
    assert "save_before_render" not in schema["properties"]
    _assert_nullable_device_schema(schema["properties"]["device"])
