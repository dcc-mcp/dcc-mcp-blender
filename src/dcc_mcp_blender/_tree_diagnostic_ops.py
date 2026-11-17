"""Tree diagnostic policy composed with Blender's shared render job owner."""

from __future__ import annotations

from pathlib import Path

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender import _render_job_ops as jobs
from dcc_mcp_blender._render_worker_receipt import file_hash
from dcc_mcp_blender._tree_diagnostic_receipt import verify_tree_preview

_KIND = "tree_diagnostic"


def _request(obj_path, material_categories, resolution):
    obj = Path(obj_path).expanduser().resolve(strict=True)
    if not obj.is_file() or obj.suffix.lower() != ".obj":
        raise ValueError("Expected an OBJ file")
    if not isinstance(material_categories, dict) or not material_categories:
        raise ValueError("An explicit material mapping is required")
    if any(not isinstance(k, str) or not k or v not in {"wood", "card"} for k, v in material_categories.items()):
        raise ValueError("Each material must map to wood or card")
    if set(material_categories.values()) != {"wood", "card"}:
        raise ValueError("Both wood and card categories must be provided")
    if type(resolution) is not int or not 128 <= resolution <= 2048:
        raise ValueError("resolution must be an integer between 128 and 2048")
    return dict(
        obj=str(obj), source_sha256=file_hash(obj), material_categories=material_categories, resolution=resolution
    )


def start_tree_diagnostic(obj_path, output_directory, material_categories, resolution=768):
    """Validate domain inputs and submit through the shared Blender worker owner."""
    try:
        request = _request(obj_path, material_categories, resolution)
        import bpy

        if tuple(bpy.app.version) < (4, 5, 0):
            raise ValueError("Blender 4.5 or newer is required")
        return jobs.submit_owned_worker(
            bpy.app.binary_path,
            Path(__file__).with_name("_tree_diagnostic_worker.py"),
            output_directory,
            _KIND,
            request,
            timeout_seconds=600,
        )
    except Exception as exc:
        return skill_exception(exc, message="Tree diagnostics could not start")


def get_tree_diagnostic(job_id, job_directory=None):
    """Recover status and verify artifacts without holding the render registry lock."""
    try:
        context = jobs.owned_worker_context(job_id, _KIND, job_directory)
        if context["status"] == "completed":
            context["manifest_path"] = verify_tree_preview(context["job_directory"])
        if context["status"] in {"failed", "timed_out", "stop_failed"}:
            for key in ("stdout", "stderr"):
                context[key + "_tail"] = jobs._log_tail(
                    context, key + "_path", allowed_directory=context["job_directory"]
                )
            return skill_error("Tree diagnostics failed", context.get("error", context["status"]), **context)
        return skill_success("Tree diagnostic status", **context)
    except Exception as exc:
        return skill_exception(exc, message="Tree diagnostic evidence unavailable", job_id=job_id)


def cancel_tree_diagnostic(job_id, job_directory=None):
    """Stop only a currently owned process; disk receipts never authorize PID reuse."""
    return jobs.cancel_owned_worker(job_id, _KIND, job_directory)
