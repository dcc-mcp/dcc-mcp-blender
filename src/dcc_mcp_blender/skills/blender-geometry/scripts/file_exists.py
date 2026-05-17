"""Check whether a file exists."""

from __future__ import annotations

import os

from dcc_mcp_core.skill import skill_entry, skill_success


def file_exists(path: str) -> dict:
    """Return whether *path* exists and its size in bytes."""
    exists = os.path.isfile(path)
    size = os.path.getsize(path) if exists else 0
    return skill_success(
        f"File {'exists' if exists else 'does not exist'}: {path}",
        filepath=path,
        exists=exists,
        size=size,
        prompt="File check complete.",
    )


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`file_exists`."""
    return file_exists(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
