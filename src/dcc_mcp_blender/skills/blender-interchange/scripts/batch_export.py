"""Run a batch of Blender exports."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._interchange_ops import batch_export


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`batch_export`."""
    return batch_export(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
