"""Cancel a specific render job on the render farm.

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


def cancel_render_job(
    job_id: str,
    farm: str = "flamenco",
    deadline_command: Optional[str] = None,
    flamenco_server_url: Optional[str] = None,
) -> dict:
    """Cancel a specific render job on the render farm.

    Args:
        job_id: The job ID returned by ``submit_render_job``.
        farm: Render farm backend (``"flamenco"`` or ``"deadline"``).
        deadline_command: Path to ``deadlinecommand`` binary (Deadline only).
        flamenco_server_url: Flamenco Manager URL (Flamenco only).

    Returns:
        ToolResult dict confirming cancellation.
    """

    try:
        if farm == "deadline":
            return _cancel_deadline_job(job_id, deadline_command)
        elif farm == "flamenco":
            return _cancel_flamenco_job(job_id, flamenco_server_url)
        else:
            return skill_error(
                "Unknown farm type: '{}'".format(farm),
                "Supported farms: flamenco, deadline",
            )
    except Exception as exc:
        return skill_exception(exc, message="Failed to cancel render job")


def _cancel_deadline_job(job_id: str, deadline_command: Optional[str]) -> dict:
    """Cancel a Deadline job via deadlinecommand."""
    from dcc_mcp_core import check_dcc_cancelled  # noqa: PLC0415

    check_dcc_cancelled()

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

    check_dcc_cancelled()

    proc = subprocess.run(
        [cmd, "-DeleteJob", job_id],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if proc.returncode != 0:
        return skill_error(
            "Failed to cancel Deadline job '{}'".format(job_id),
            proc.stderr.strip() or proc.stdout.strip(),
        )

    return skill_success(
        "Cancelled Deadline job '{}'".format(job_id),
        prompt="Use list_render_jobs to verify the job was removed.",
        job_id=job_id,
        farm="deadline",
        cancelled=True,
    )


def _cancel_flamenco_job(job_id: str, flamenco_server_url: Optional[str]) -> dict:
    """Cancel a Flamenco job via REST API.

    Uses the official Flamenco v3 API endpoint:
    ``POST /api/v3/jobs/{job_id}/setstatus`` with body ``{"status": "cancel-requested"}``.
    """
    try:
        import urllib.error  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        from dcc_mcp_core import check_dcc_cancelled  # noqa: PLC0415

        server_url = flamenco_server_url or os.environ.get("FLAMENCO_SERVER_URL", "http://localhost:8080")
        server_url = server_url.rstrip("/")

        check_dcc_cancelled()

        api_url = "{}/api/v3/jobs/{}/setstatus".format(server_url, job_id)
        payload = json.dumps({"status": "cancel-requested"}).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            _result = json.loads(resp.read().decode("utf-8"))

        return skill_success(
            "Cancelled Flamenco job '{}'".format(job_id),
            prompt="Use get_render_job_status to confirm the cancellation.",
            job_id=job_id,
            farm="flamenco",
            cancelled=True,
            server_url=server_url,
        )
    except ImportError:
        return skill_error(
            "urllib not available",
            "Python standard library was stripped; install python or use deadline farm",
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            return skill_error(
                "Cannot cancel Flamenco job '{}': job is in a non-cancellable state".format(job_id),
                "The job may already be completed or cancelled. HTTP 409: {}".format(str(exc)),
            )
        return skill_error(
            "Flamenco API error (HTTP {})".format(exc.code),
            str(exc),
        )


@skill_entry
def main(**kwargs):
    return cancel_render_job(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
