"""Run pytest E2E tests inside a real Blender background process."""

from __future__ import annotations

import os
import sys


def main() -> int:
    workspace = os.environ.get("GITHUB_WORKSPACE", ".")
    dep_dir = os.environ.get("BLENDER_E2E_SITE")
    if dep_dir and os.path.isdir(dep_dir) and dep_dir not in sys.path:
        sys.path.insert(0, dep_dir)

    if workspace not in sys.path:
        sys.path.insert(0, workspace)

    src_dir = os.path.join(workspace, "src")
    if os.path.isdir(src_dir) and src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    import pytest

    exit_code = pytest.main(
        [
            os.path.join(workspace, "tests", "e2e"),
            "-v",
            "--tb=short",
            "-m",
            "e2e",
            "--override-ini=addopts=",
        ]
    )
    return 0 if exit_code == 5 else exit_code


if __name__ == "__main__":
    # Bypass Blender C++ cleanup in Linux background mode; sys.exit() can
    # otherwise try to destroy uninitialized X11/OpenGL resources.
    os._exit(main())
