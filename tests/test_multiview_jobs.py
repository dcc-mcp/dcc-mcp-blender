from unittest.mock import MagicMock

import pytest

from dcc_mcp_blender import _render_job_ops as jobs
from dcc_mcp_blender._multiview_receipt import multiview_context, png_evidence, write_receipt


@pytest.fixture(autouse=True)
def _isolated_jobs():
    """Keep registered worker handles from leaking between tests."""
    jobs._JOBS.clear()
    yield
    jobs._JOBS.clear()


def receipt(tmp_path, status="running"):
    result = dict(
        job_id="test",
        kind="multiview",
        status=status,
        items=[{"camera": "Camera", "pass": "beauty", "status": "pending"}],
    )
    write_receipt(tmp_path, result)
    return result


def test_recovery_does_not_claim_live_worker(tmp_path):
    receipt(tmp_path)
    result = jobs.get_render_job("test", str(tmp_path))
    assert result["success"]
    assert result["context"]["status"] == "unknown"
    assert result["context"]["last_recorded_status"] == "running"
    assert result["context"]["process_observed"] is False


def test_cancel_recovered_job_does_not_kill_pid(tmp_path, monkeypatch):
    receipt(tmp_path)
    kill = MagicMock()
    monkeypatch.setattr(jobs, "_terminate_process_tree", kill)
    result = jobs.cancel_render_job("test", str(tmp_path))
    assert result["success"]
    assert result["context"]["cancellation_requested"]
    assert (tmp_path / "cancel").is_file()
    kill.assert_not_called()


def test_wrong_receipt_identity_is_rejected(tmp_path):
    receipt(tmp_path)
    assert not jobs.get_render_job("other", str(tmp_path))["success"]
    assert not jobs.cancel_render_job("other", str(tmp_path))["success"]
    assert not (tmp_path / "cancel").exists()


def test_worker_crash_marks_unfinished_items_failed(tmp_path):
    receipt(tmp_path)
    process = MagicMock()
    process.poll.return_value = 2
    result = multiview_context(dict(job_id="test", job_directory=str(tmp_path), process=process))
    assert result["status"] == "failed"
    assert result["items"][0]["status"] == "failed"
    assert jobs.get_render_job("test", str(tmp_path))["context"]["status"] == "failed"


def _register_live_process(tmp_path, process):
    """Attach a worker handle so recovery observes a real exit."""
    jobs._JOBS["test"] = dict(job_id="test", kind="multiview", job_directory=str(tmp_path), process=process)


def test_failed_recovery_quotes_the_receipt_error_not_missing_tails(tmp_path):
    """The failure message only references fields the context really has.

    A multiview context never carries log tails, so pointing the caller at
    ``stderr_tail`` used to name keys that do not exist while hiding the
    receipt's own ``error``.
    """
    receipt(tmp_path)
    jobs._JOBS.clear()
    process = MagicMock()
    process.poll.return_value = 2
    _register_live_process(tmp_path, process)

    result = jobs.get_render_job("test", str(tmp_path))

    context = result["context"]
    assert context["status"] == "failed"
    assert "code 2" in result["message"], result["message"]
    assert "stderr_tail" not in result["message"]
    # The tails themselves are still attached, so the message is not a dead end.
    assert context["stderr_tail"] == ""
    assert context["stdout_tail"] == ""


def test_failed_recovery_reads_whichever_log_the_worker_used(tmp_path):
    """Recovery surfaces a device error written to either worker log.

    The advice is multiview-specific: ``start_multiview_render_job`` takes no
    ``device`` argument, so pointing the caller at ``start_render_job`` would
    drop the camera and pass list.
    """
    receipt(tmp_path)
    jobs._JOBS.clear()
    (tmp_path / "stdout.log").write_text(
        "00:01.687  reports | ERROR Found no Cycles device of the specified type\n",
        encoding="utf-8",
    )
    process = MagicMock()
    process.poll.return_value = 2
    _register_live_process(tmp_path, process)

    context = jobs.get_render_job("test", str(tmp_path))["context"]

    assert context["status"] == "failed"
    hint = context["failure_hint"]
    assert "start_multiview_render_job" in hint
    assert "start_render_job" not in hint
    assert "CPU" in hint


def test_recovery_refuses_a_symlinked_worker_log(tmp_path):
    """A caller-supplied job_directory must not reach files outside it.

    ``read_receipt`` only proves the directory holds a matching receipt, not
    that it owns the log files beside it. Without this check a crafted
    directory could symlink ``stdout.log`` at any file on the host and have
    its tail returned as tool output -- a prompt-injection sink.
    """
    receipt(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("BEGIN " + "A" * 20000 + " END-CANARY", encoding="utf-8")
    try:
        (tmp_path / "stdout.log").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this host")
    process = MagicMock()
    process.poll.return_value = 2
    _register_live_process(tmp_path, process)

    context = jobs.get_render_job("test", str(tmp_path))["context"]

    assert context["status"] == "failed"
    assert "END-CANARY" not in context["stdout_tail"]
    assert context["stdout_tail"] == ""


def test_recovery_ignores_a_log_outside_the_job_directory(tmp_path):
    """A log path that escapes job_directory is not read."""
    receipt(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "stdout.log").write_text("BEGIN " + "B" * 9000 + " END-CANARY", encoding="utf-8")
    job = dict(
        job_id="test",
        kind="multiview",
        job_directory=str(tmp_path),
    )

    context = jobs._failed_job_context(
        dict(
            job,
            status="failed",
            stdout_path=str(outside / "stdout.log"),
            stderr_path=str(tmp_path / "stderr.log"),
        )
    )

    assert context["stdout_tail"] == ""
    assert "END-CANARY" not in context["stdout_tail"]


def test_completed_output_is_rechecked_not_just_file_exists(tmp_path):
    result = receipt(tmp_path, "completed")
    # Receipt verification hashes the worker-decoded PNG, not only its magic.
    path = tmp_path / "00_beauty.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (16).to_bytes(4, "big") * 2 + b"original")
    result["items"][0].update(status="completed", image=png_evidence(path))
    write_receipt(tmp_path, result)
    path.write_bytes(path.read_bytes()[:-1] + b"X")
    result = jobs.get_render_job("test", str(tmp_path))["context"]
    assert result["status"] == "failed"
    assert result["items"][0]["status"] == "failed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("camera_names", []),
        ("camera_names", ["A"] * 9),
        ("passes", ["wire", "wire"]),
        ("resolution_x", 4097),
        ("wire_radius", float("nan")),
    ],
)
def test_preflight_rejects_invalid_arguments_before_saving(tmp_path, monkeypatch, field, value):
    from dcc_mcp_blender._multiview_ops import start_multiview_render_job

    bpy = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "bpy", bpy)
    args = dict(output_directory=str(tmp_path), camera_names=["A"])
    args[field] = value
    assert not start_multiview_render_job(**args)["success"]
    bpy.ops.wm.save_as_mainfile.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_wire_contract_is_discoverable():
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[1] / "src/dcc_mcp_blender/skills/blender-render"
    contracts = {tool["name"]: tool for tool in yaml.safe_load((root / "tools.yaml").read_text())["tools"]}
    contract = contracts["start_multiview_render_job"]
    assert contract["job_strategy"] == "isolated"
    assert contract["affinity"] == "main"
    assert contract["input_schema"]["properties"]["camera_names"]["maxItems"] == 8
    assert "job_directory" in contracts["get_render_job"]["input_schema"]["properties"]
    assert "job_directory" in contracts["cancel_render_job"]["input_schema"]["properties"]


def test_worker_observes_cancel_before_first_image(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(jobs.__file__).with_name("_multiview_worker.py")
    spec = importlib.util.spec_from_file_location("test_multiview_worker", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    receipt(tmp_path)
    (tmp_path / "request.json").write_text('{"job_id":"test"}')
    (tmp_path / "cancel").touch()
    bpy = MagicMock()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    worker.run(tmp_path)
    result = jobs.get_render_job("test", str(tmp_path))["context"]
    assert result["status"] == "cancelled"
    assert result["items"][0]["status"] == "cancelled"
    bpy.ops.wm.open_mainfile.assert_not_called()


def test_corrupt_earlier_image_does_not_claim_running_worker_stopped(tmp_path):
    result = receipt(tmp_path)
    result["items"][0].update(status="completed", image={})
    write_receipt(tmp_path, result)
    process = MagicMock()
    process.poll.return_value = None
    context = multiview_context(dict(job_id="test", job_directory=str(tmp_path), process=process))
    assert context["status"] == "running"
    assert context["items"][0]["status"] == "failed"


@pytest.mark.parametrize("budget", [0, 500001, True, 1.5])
def test_source_edge_budget_is_validated(tmp_path, monkeypatch, budget):
    import sys

    from dcc_mcp_blender._multiview_ops import start_multiview_render_job

    bpy = MagicMock()
    bpy.context.scene.objects.get.return_value.type = "CAMERA"
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    result = start_multiview_render_job(str(tmp_path), ["Camera"], max_source_edges=budget)
    assert not result["success"]
    bpy.ops.wm.save_as_mainfile.assert_not_called()


@pytest.mark.parametrize("executable", ["cache/Blender.app/Blender", "./Blender"])
def test_worker_resolves_relative_executable_before_changing_cwd(tmp_path, monkeypatch, executable):
    monkeypatch.chdir(tmp_path)
    popen = MagicMock()
    monkeypatch.setattr(jobs.subprocess, "Popen", popen)
    output = tmp_path / "output"
    output.mkdir()
    jobs._launch_worker([executable, "--background"], output, output / "out", output / "err")
    assert popen.call_args.args[0][0] == str((tmp_path / executable).resolve())
    assert popen.call_args.kwargs["cwd"] == str(output)
