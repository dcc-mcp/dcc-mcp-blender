"""Export normalized Blender modeling state."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._model_state import export_model_state


@skill_entry
def main(**kwargs) -> dict:
    """Entry point for the model-state export tool."""
    return export_model_state(**kwargs)


if __name__ == "__main__":
    run_main(main)
