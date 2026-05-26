"""Get Blender Python environment diagnostics."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._dev_ops import get_python_environment


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_python_environment`."""
    return get_python_environment(**kwargs)


if __name__ == "__main__":
    run_main(main)
