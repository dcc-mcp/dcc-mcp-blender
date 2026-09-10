"""Published camera schemas must be usable without importing bpy scripts."""

import inspect

import jsonschema
import yaml

from tests.conftest import SKILLS_ROOT, load_skill_script


def test_camera_schemas_describe_script_arguments_and_examples():
    tools = yaml.safe_load((SKILLS_ROOT / "blender-camera" / "tools.yaml").read_text())["tools"]
    for tool in tools:
        schema = tool["input_schema"]
        jsonschema.Draft202012Validator.check_schema(schema)
        module = load_skill_script("blender-camera", tool["name"])
        signature = inspect.signature(getattr(module, tool["name"]))
        assert set(schema["properties"]) == set(signature.parameters)
        required = [key for key, value in signature.parameters.items() if value.default is inspect.Parameter.empty]
        assert sorted(schema.get("required", [])) == sorted(required)
        assert tool["enforce_thread_affinity"] is True
        for example in tool["call_examples"]:
            jsonschema.validate(example["arguments"], schema)
