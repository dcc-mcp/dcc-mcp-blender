"""Offline ownership, recovery and concurrency contracts for tree diagnostics."""

import json
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from dcc_mcp_blender import _render_job_ops as jobs
from dcc_mcp_blender import _tree_diagnostic_ops as diagnostics
from dcc_mcp_blender import _tree_diagnostic_receipt as evidence
from dcc_mcp_blender._render_worker_receipt import file_hash


class Process:
    pid = 123

    def __init__(self):
        self.returncode = None
        self.done = threading.Event()

    def poll(self):
        return self.returncode

    def finish(self, code=0):
        self.returncode = code
        self.done.set()

    def terminate(self):
        self.finish(-15)

    kill = terminate

    def wait(self, timeout=None):
        if not self.done.wait(timeout):
            raise subprocess.TimeoutExpired("synthetic-worker", timeout)
        return self.returncode


@pytest.fixture
def worker(tmp_path, monkeypatch):
    processes = []
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(jobs, "_OWNED_WORKERS_ACCEPTING", True)
    obj = tmp_path / "source.obj"
    obj.write_text("# synthetic OBJ", encoding="utf-8")
    binary = tmp_path / "blender.exe"
    binary.write_bytes(b"fixture")
    monkeypatch.setitem(
        sys.modules,
        "bpy",
        types.SimpleNamespace(
            app=types.SimpleNamespace(
                binary_path=str(binary), version=(5, 1, 0), version_string="5.1.0", background=True
            )
        ),
    )

    def launch(*args):
        process = Process()
        processes.append(process)
        return process

    monkeypatch.setattr(jobs, "_launch_worker", launch)
    monkeypatch.setattr(jobs, "_terminate_process_tree", lambda process: process.terminate())

    def start():
        result = diagnostics.start_tree_diagnostic(str(obj), str(tmp_path), {"Wood": "wood", "Card": "card"}, 128)
        return result, processes[-1] if processes else None

    yield start
    for process in processes:
        process.terminate()
    jobs.stop_owned_workers()


def completed(worker):
    result, process = worker()
    assert result["success"], result
    jid = result["context"]["job_id"]
    directory = Path(result["context"]["job_directory"])
    request = json.loads((directory / "request.json").read_text())
    names = {
        "{}_{}{}.png".format(k, v, s)
        for k in ("full", "bare")
        for v in ("front", "back", "left", "right")
        for s in ("", "_mask")
    }
    names.add("card_closeup.png")
    for name in names:
        (directory / name).write_bytes(b"synthetic image evidence; not a native render")
    manifest = {
        "source": {"sha256": request["source_sha256"]},
        "images": {name: file_hash(directory / name) for name in names},
    }
    (directory / "preview-manifest.json").write_text(json.dumps(manifest))
    process.finish()
    for _ in range(100):
        if diagnostics.get_tree_diagnostic(jid).get("context", {}).get("status") == "completed":
            break
        time.sleep(0.01)
    assert diagnostics.get_tree_diagnostic(jid)["context"]["status"] == "completed"
    return jid, directory


def test_reject_missing_mapping(tmp_path):
    obj = tmp_path / "source.obj"
    obj.write_text("# fixture")
    assert not diagnostics.start_tree_diagnostic(str(obj), str(tmp_path), {"wood": "wood"})["success"]
    assert not list(tmp_path.glob("tree-diagnostic-*"))


def test_reject_unknown_job():
    assert not diagnostics.get_tree_diagnostic("not-owned")["success"]
    assert not diagnostics.cancel_tree_diagnostic("not-owned")["success"]


def test_owned_worker_cancellation(worker):
    result, process = worker()
    jid = result["context"]["job_id"]
    assert diagnostics.cancel_tree_diagnostic(jid)["context"]["cancellation_requested"]
    assert process.poll() is not None
    assert diagnostics.get_tree_diagnostic(jid)["context"]["status"] == "cancelled"


def test_deadline_stops_owned_worker(worker):
    result, process = worker()
    jid = result["context"]["job_id"]
    jobs._watch_owned_worker(jobs._JOBS[jid], 0.01)
    assert process.poll() is not None
    state = diagnostics.get_tree_diagnostic(jid)
    assert not state["success"] and state["context"]["status"] == "timed_out"


def test_thread_start_failure_reaps_process_and_returns_identity(worker, monkeypatch):
    def fail(*args):
        raise RuntimeError("synthetic thread-start failure")

    monkeypatch.setattr(threading.Thread, "start", fail)
    result, process = worker()
    assert not result["success"]
    assert result["context"]["job_id"] and result["context"]["job_directory"]
    assert process.poll() is not None
    assert result["context"]["status"] == "failed"


def test_terminal_receipt_recovers_without_process_authority(worker):
    jid, directory = completed(worker)
    jobs._JOBS.pop(jid)
    state = diagnostics.get_tree_diagnostic(jid, str(directory))
    assert state["success"] and state["context"]["status"] == "completed"
    assert not state["context"]["process_observed"]
    assert not diagnostics.cancel_tree_diagnostic(jid, str(directory))["success"]
    (directory / "full_front.png").write_bytes(b"tampered")
    assert not diagnostics.get_tree_diagnostic(jid, str(directory))["success"]


def test_running_receipt_recovers_as_unknown(worker):
    result, _ = worker()
    context = result["context"]
    jobs._JOBS.pop(context["job_id"])
    state = diagnostics.get_tree_diagnostic(context["job_id"], context["job_directory"])
    assert state["success"] and state["context"]["status"] == "unknown"
    assert state["context"]["last_recorded_status"] == "running"


def test_wrong_job_and_changed_request_fail_closed(worker):
    jid, directory = completed(worker)
    assert not diagnostics.get_tree_diagnostic("different-id", str(directory))["success"]
    (directory / "request.json").write_text("{}")
    assert not diagnostics.get_tree_diagnostic(jid, str(directory))["success"]


@pytest.mark.parametrize("operation", ["cancel", "deadline", "shutdown"])
def test_evidence_io_does_not_block_other_worker_stop(worker, monkeypatch, operation):
    jid, _ = completed(worker)
    other, process = worker()
    other_id = other["context"]["job_id"]
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    original = evidence.file_hash

    def slow_hash(path):
        entered.set()
        assert release.wait(3)
        return original(path)

    monkeypatch.setattr(evidence, "file_hash", slow_hash)
    reader = threading.Thread(target=diagnostics.get_tree_diagnostic, args=(jid,))
    reader.start()
    assert entered.wait(1)

    def stop():
        if operation == "cancel":
            diagnostics.cancel_tree_diagnostic(other_id)
        elif operation == "deadline":
            jobs._watch_owned_worker(jobs._JOBS[other_id], 0.01)
        else:
            jobs.stop_owned_workers()
        stopped.set()

    stopper = threading.Thread(target=stop)
    stopper.start()
    try:
        assert stopped.wait(1), "Evidence IO blocked another worker's lifecycle"
        assert process.poll() is not None
    finally:
        release.set()
        reader.join(3)
        stopper.join(3)


def test_bounded_admission_and_shutdown(worker):
    assert worker()[0]["success"]
    assert worker()[0]["success"]
    rejected, _ = worker()
    assert not rejected["success"]
    assert len(jobs._JOBS) == 2
    jobs.stop_owned_workers()
    assert not worker()[0]["success"]
    jobs.resume_owned_workers()
    assert worker()[0]["success"]


def test_adapter_stop_uses_core_quit_hook(worker):
    from dcc_mcp_blender.server import BlenderMcpServer

    server = BlenderMcpServer(port=0)
    result, process = worker()
    server.stop()
    assert process.poll() is not None
    assert diagnostics.get_tree_diagnostic(result["context"]["job_id"])["context"]["status"] == "host_shutdown"
    assert not worker()[0]["success"]


def test_typed_wrappers_share_the_host_execution_bridge(worker):
    from dcc_mcp_core import HostExecutionBridge

    result, _ = worker()
    jid = result["context"]["job_id"]
    bridge = HostExecutionBridge()
    scripts = Path(diagnostics.__file__).parent / "skills" / "blender-render" / "scripts"
    state = bridge.execute_script(
        str(scripts / "get_tree_diagnostic.py"), {"job_id": jid}, skill_name="blender-render", thread_affinity="any"
    )
    assert state["success"], state
    cancelled = bridge.execute_script(
        str(scripts / "cancel_tree_diagnostic.py"), {"job_id": jid}, skill_name="blender-render", thread_affinity="any"
    )
    assert cancelled["success"], cancelled
    assert diagnostics.get_tree_diagnostic(jid)["context"]["status"] == "cancelled"


def test_obj_names_and_non_texture_mtl_quotes_do_not_break_parsing(tmp_path):
    from dcc_mcp_blender import _tree_diagnostic_worker as worker_script

    library = tmp_path / "wood.mtl"
    library.write_text('newmtl "Bob\n# \'note\nmap_Kd "unterminated\n', encoding="utf-8")
    obj = tmp_path / "tree.obj"
    obj.write_text("o Bob's tree\nmtllib wood.mtl\n", encoding="utf-8")
    assert worker_script._obj_material_libraries(obj) == [library]
    assert "Malformed MTL texture line" in worker_script._texture_warnings([library])[0]
    obj.write_text('mtllib "unterminated\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed OBJ"):
        worker_script._obj_material_libraries(obj)


def test_projected_closeup_covers_rotated_card():
    import math

    from dcc_mcp_blender._tree_diagnostic_worker import _projected_scale

    c = math.sqrt(0.5)
    right, up = (c, c, 0), (0, 0, 1)
    points = [(x * c, x * c, z) for x in (-0.5, 0.5) for z in (-0.1, 0.1)]
    scale = _projected_scale(points, right, up, (0, 0, 0))
    assert scale == pytest.approx(1.35)
    assert scale > 1.0


def test_timeout_exit_race_still_records_failure(worker, monkeypatch):
    result, process = worker()
    job = jobs._JOBS[result["context"]["job_id"]]
    process.finish(1)

    def timed_out(timeout=None):
        raise subprocess.TimeoutExpired("exit-race", timeout)

    monkeypatch.setattr(process, "wait", timed_out)
    jobs._watch_owned_worker(job, 0.01)
    state = diagnostics.get_tree_diagnostic(job["job_id"])
    assert not state["success"] and state["context"]["status"] == "failed"


def test_failed_receipt_preserves_error_status_and_log_tails(worker):
    from dcc_mcp_blender._render_worker_receipt import read_worker_status, write_worker_status

    result, process = worker()
    jid = result["context"]["job_id"]
    directory = Path(result["context"]["job_directory"])
    receipt = read_worker_status(directory, jid, "tree_diagnostic")
    receipt.update(status="failed", error="Synthetic missing material library")
    write_worker_status(directory, receipt)
    (directory / "stderr.log").write_text("material-library failure detail")
    (directory / "stdout.log").write_text("worker started")
    process.finish(1)
    state = diagnostics.get_tree_diagnostic(jid)
    assert not state["success"]
    assert state["error"] == "Synthetic missing material library"
    assert state["context"]["status"] == "failed"
    assert state["context"]["stderr_tail"] == "material-library failure detail"
    assert state["context"]["stdout_tail"] == "worker started"
    jobs._JOBS.pop(jid)
    recovered = diagnostics.get_tree_diagnostic(jid, str(directory))
    assert not recovered["success"] and recovered["context"]["status"] == "failed"
    cancelled = diagnostics.cancel_tree_diagnostic(jid, str(directory))
    assert not cancelled["success"]
    assert cancelled["error"] == "No live process handle is owned"
    assert cancelled["context"]["worker_error"] == "Synthetic missing material library"
