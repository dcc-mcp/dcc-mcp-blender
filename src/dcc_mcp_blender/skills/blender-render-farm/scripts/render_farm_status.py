"""Report the connected render farm health and worker status.

Queries Deadline or Flamenco for current farm health, available workers,
and queue statistics.
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


def render_farm_status(
    farm: str = "flamenco",
    deadline_command: Optional[str] = None,
    flamenco_server_url: Optional[str] = None,
) -> dict:
    """Report the connected render farm health and worker status.

    Args:
        farm: Render farm backend (``"flamenco"`` or ``"deadline"``).
        deadline_command: Path to ``deadlinecommand`` binary (Deadline only).
        flamenco_server_url: Flamenco Manager URL (Flamenco only).

    Returns:
        ToolResult dict with farm status, workers, and queue summary.
    """

    try:
        if farm == "deadline":
            return _query_deadline_status(deadline_command)
        elif farm == "flamenco":
            return _query_flamenco_status(flamenco_server_url)
        else:
            return skill_error(
                "Unknown farm type: '{}'".format(farm),
                "Supported farms: flamenco, deadline",
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to query render farm status")


def _query_deadline_status(deadline_command: Optional[str]) -> dict:
    """Query Deadline farm status via deadlinecommand."""
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

    # Query slave list for worker availability
    proc = subprocess.run(
        [cmd, "-GetSlaveNames"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    workers = []
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line:
                workers.append({"name": line, "status": "online"})

    # Query pulse stats for queue info
    pulse_proc = subprocess.run(
        [cmd, "-GetPulseStats"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    pulse_info = {}  # type: dict
    if pulse_proc.returncode == 0:
        for line in pulse_proc.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                pulse_info[k.strip()] = v.strip()

    return skill_success(
        "Deadline farm status: {} worker(s), {} queued job(s)".format(
            len(workers),
            pulse_info.get("QueuedJobsCount", "0"),
        ),
        prompt="Use list_render_jobs to see job details.",
        farm="deadline",
        workers=workers,
        worker_count=len(workers),
        queue_stats=pulse_info,
        healthy=proc.returncode == 0,
    )


def _query_flamenco_status(flamenco_server_url: Optional[str]) -> dict:
    """Query Flamenco Manager health and worker status via REST API."""
    try:
        import urllib.error  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        server_url = flamenco_server_url or os.environ.get("FLAMENCO_SERVER_URL", "http://localhost:8080")
        server_url = server_url.rstrip("/")

        # Query manager config/health
        workers_url = "{}/api/v3/workers".format(server_url)
        req = urllib.request.Request(workers_url, headers={"Accept": "application/json"}, method="GET")

        workers = []
        worker_count = 0
        healthy = True

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                workers_data = json.loads(resp.read().decode("utf-8"))
                workers = workers_data.get("workers", workers_data if isinstance(workers_data, list) else [])
                worker_count = len(workers)
        except urllib.error.HTTPError as exc:
            healthy = False
            workers = [{"error": "HTTP {}: {}".format(exc.code, str(exc))}]
        except Exception as exc:
            healthy = False
            workers = [{"error": str(exc)}]

        # Query job queue summary
        queue_stats = {}
        try:
            queue_url = "{}/api/v3/jobs/queue".format(server_url)
            queue_req = urllib.request.Request(queue_url, headers={"Accept": "application/json"}, method="GET")
            with urllib.request.urlopen(queue_req, timeout=30) as resp:
                queue_data = json.loads(resp.read().decode("utf-8"))
                queue_stats = {
                    "queued": queue_data.get("length", 0) if isinstance(queue_data, dict) else len(queue_data),
                }
        except Exception:
            pass

        return skill_success(
            "Flamenco farm status: {} worker(s), {} queued job(s)".format(
                worker_count,
                queue_stats.get("queued", 0),
            ),
            prompt="Use list_render_jobs to see job details.",
            farm="flamenco",
            workers=workers,
            worker_count=worker_count,
            queue_stats=queue_stats,
            healthy=healthy,
            server_url=server_url,
        )
    except ImportError:
        return skill_error(
            "urllib not available",
            "Python standard library was stripped; install python or use deadline farm",
        )
    except Exception as exc:
        return skill_error(
            "Failed to query Flamenco farm status",
            str(exc),
        )


@skill_entry
def main(**kwargs):
    return render_farm_status(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
