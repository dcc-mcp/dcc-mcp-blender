"""List recent render jobs from the farm manager.

Supports Deadline and Flamenco backends.
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


def list_render_jobs(
    farm: str = "flamenco",
    limit: int = 20,
    status_filter: Optional[str] = None,
    deadline_command: Optional[str] = None,
    flamenco_server_url: Optional[str] = None,
) -> dict:
    """List recent render jobs from the farm manager.

    Args:
        farm: Render farm backend (``"flamenco"`` or ``"deadline"``).
        limit: Maximum number of jobs to return.  Default: 20.
        status_filter: Optional filter by job status (e.g. ``"queued"``, ``"active"``, ``"completed"``).
        deadline_command: Path to ``deadlinecommand`` binary (Deadline only).
        flamenco_server_url: Flamenco Manager URL (Flamenco only).

    Returns:
        ToolResult dict with ``context.jobs`` list and ``context.count``.
    """

    try:
        if farm == "deadline":
            return _list_deadline_jobs(limit, status_filter, deadline_command)
        elif farm == "flamenco":
            return _list_flamenco_jobs(limit, status_filter, flamenco_server_url)
        else:
            return skill_error(
                "Unknown farm type: '{}'".format(farm),
                "Supported farms: flamenco, deadline",
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list render jobs")


def _list_deadline_jobs(
    limit: int,
    status_filter: Optional[str],
    deadline_command: Optional[str],
) -> dict:
    """List Deadline jobs via deadlinecommand."""
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

    args = [cmd, "-GetJobs"]
    if status_filter:
        args.extend(["-Status", status_filter])
    args.extend(["-Limit", str(limit)])

    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if proc.returncode != 0:
        return skill_error(
            "Failed to list Deadline jobs",
            proc.stderr.strip() or proc.stdout.strip(),
        )

    # Parse multi-line output — each job is separated by an empty line
    jobs = []
    current_job = {}  # type: dict
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            if current_job:
                jobs.append(current_job)
                current_job = {}
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            current_job[k.strip()] = v.strip()
    if current_job:
        jobs.append(current_job)

    return skill_success(
        "Found {} Deadline job(s)".format(len(jobs)),
        prompt="Use get_render_job_status with a specific job_id to get details.",
        farm="deadline",
        count=len(jobs),
        jobs=jobs,
    )


def _list_flamenco_jobs(
    limit: int,
    status_filter: Optional[str],
    flamenco_server_url: Optional[str],
) -> dict:
    """List Flamenco jobs via REST API."""
    try:
        import urllib.error  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        from dcc_mcp_core import check_dcc_cancelled  # noqa: PLC0415

        server_url = flamenco_server_url or os.environ.get("FLAMENCO_SERVER_URL", "http://localhost:8080")
        server_url = server_url.rstrip("/")

        check_dcc_cancelled()

        api_url = "{}/api/v3/jobs?limit={}".format(server_url, limit)
        if status_filter:
            api_url += "&status={}".format(status_filter)

        req = urllib.request.Request(api_url, headers={"Accept": "application/json"}, method="GET")

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        jobs = result.get("jobs", result if isinstance(result, list) else [])

        return skill_success(
            "Found {} Flamenco job(s)".format(len(jobs)),
            prompt="Use get_render_job_status with a specific job_id to get details.",
            farm="flamenco",
            count=len(jobs),
            jobs=jobs,
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
            "Failed to list Flamenco jobs",
            str(exc),
        )


@skill_entry
def main(**kwargs):
    return list_render_jobs(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
