from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_blender._text_geometry import inspect_text


@skill_entry
def main(**kwargs):
    return inspect_text(**kwargs)


if __name__ == "__main__":
    run_main(main)
