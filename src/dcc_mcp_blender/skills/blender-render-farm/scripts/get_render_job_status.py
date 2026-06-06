"""Query the status of a submitted render job by job ID.

Supports Deadline, Flamenco, and generic farm backends.
"""

# Import future modules
from __future__ import annotations

# Import built-in modules
import json
import os
import subprocess
from typing import Optional

# Import local modules
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_render_job_status(
    job_id: str,
    farm: str = "flamenco",
    deadline_command: Optional[str] = None,
    flamenco_server_url: Optional[str] = None,
) -> dict:
    """Query the render farm for the status of a render job.

    Args:
        job_id: The job ID returned by ``submit_render_job``.
        farm: Render farm backend (``"flamenco"`` or ``"deadline"``).
        deadline_command: Path to ``deadlinecommand`` binary (Deadline only).
        flamenco_server_url: Flamenco Manager URL (Flamenco only).

    Returns:
        ToolResult dict with job status, progress, and task summary.
    """

    try:
        if farm == "deadline":
            return _query_deadline(job_id, deadline_command)
        elif farm == "flamenco":
            return _query_flamenco(job_id, flamenco_server_url)
        else:
            return skill_error(
                "Unknown farm type: '{}'".format(farm),
                "Supported farms: flamenco, deadline",
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to query job status")


def _query_deadline(job_id: str, deadline_command: Optional[str]) -> dict:
    """Query Deadline for job status via deadlinecommand."""
    cmd = deadline_command
    if not cmd:
        for candidate in ["deadlinecommand", "deadlinecommand.exe"]:
            result = subprocess.run(
                ["where", candidate] if os.name == "nt" else ["which", candidate],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                cmd = candidate
                break
    if not cmd:
        return skill_error(
            "deadlinecommand not found",
            "Install Thinkbox Deadline client and ensure it is on PATH",
        )

    proc = subprocess.run(
        [cmd, "-GetJobDetails", job_id],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if proc.returncode != 0:
        return skill_error(
            "Failed to query job '{}'".format(job_id),
            proc.stderr.strip() or proc.stdout.strip(),
        )

    # Parse key=value output
    status_info = {}  # type: dict
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            status_info[k.strip()] = v.strip()

    job_status = status_info.get("Status", "Unknown")
    completed = status_info.get("CompletedChunks", "0")
    total = status_info.get("TaskCount", "0")
    errors = status_info.get("FailedChunks", "0")

    return skill_success(
        "Job '{}' status: {} ({}/{} tasks)".format(job_id, job_status, completed, total),
        prompt="Check again later or use submit_render_job to resubmit if failed.",
        job_id=job_id,
        farm="deadline",
        status=job_status,
        completed_tasks=completed,
        total_tasks=total,
        failed_tasks=errors,
        raw=status_info,
    )


def _query_flamenco(job_id: str, flamenco_server_url: Optional[str]) -> dict:
    """Query Flamenco Manager API for job status."""
    try:
        import urllib.error  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        from dcc_mcp_core import check_dcc_cancelled  # noqa: PLC0415

        server_url = flamenco_server_url or os.environ.get("FLAMENCO_SERVER_URL", "http://localhost:8080")
        server_url = server_url.rstrip("/")

        check_dcc_cancelled()

        api_url = "{}/api/v3/jobs/{}".format(server_url, job_id)
        req = urllib.request.Request(api_url, headers={"Accept": "application/json"}, method="GET")

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        job_status = result.get("status", "unknown")
        task_summary = result.get("task_summary", {})
        completed = task_summary.get("completed", 0)
        total = task_summary.get("total", 0)
        failed = task_summary.get("failed", 0)

        return skill_success(
            "Job '{}' status: {} ({}/{} tasks)".format(job_id, job_status, completed, total),
            prompt="Check again later or use submit_render_job to resubmit if failed.",
            job_id=job_id,
            farm="flamenco",
            status=job_status,
            completed_tasks=completed,
            total_tasks=total,
            failed_tasks=failed,
            name=result.get("name", ""),
            server_url=server_url,
        )
    except ImportError:
        return skill_error(
            "urllib not available",
            "Python standard library was stripped; install python or use deadline farm",
        )
    except urllib.error.HTTPError as exc:
        return skill_error(
            "Flamenco API error (HTTP {})".format(exc.code),
            str(exc),
        )
    except Exception as exc:
        return skill_error(
            "Failed to query Flamenco job '{}'".format(job_id),
            str(exc),
        )


@skill_entry
def main(**kwargs):
    return get_render_job_status(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
