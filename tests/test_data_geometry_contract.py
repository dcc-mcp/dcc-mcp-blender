"""Pure input-contract tests; actual Blender acceptance has separate receipts."""

import importlib.util
import json
import unittest
from pathlib import Path

from jsonschema import Draft7Validator

PATH = Path(__file__).resolve().parents[1] / "src/dcc_mcp_blender/_data_geometry.py"
spec = importlib.util.spec_from_file_location("data_geometry_contract", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GeometryContractTests(unittest.TestCase):
    def setUp(self):
        self.vertices = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]

    def test_valid_mesh_preserves_topology(self):
        pts, faces = module.validate_mesh_data("Island", self.vertices, [[0, 1, 2, 3]])
        self.assertEqual(faces, [(0, 1, 2, 3)])
        self.assertEqual(pts[1], (1.0, 0.0, 0.0))

    def test_invalid_mesh_inputs(self):
        cases = [
            ([], [[0, 1, 2]]),
            (self.vertices, [[0, 1, 4]]),
            (self.vertices, [[0, 1, 1]]),
            (self.vertices, [[0, True, 2]]),
            ([[0, 0, float("nan")]] * 3, [[0, 1, 2]]),
            ([[0, 0, float("inf")]] * 3, [[0, 1, 2]]),
            ([[0, 0, 1000001]] * 3, [[0, 1, 2]]),
            ([[0, 0, 0]] * 30001, [[0, 1, 2]]),
        ]
        for pts, faces in cases:
            with self.subTest(pts=str(pts)[:60], faces=faces):
                with self.assertRaises(ValueError):
                    module.validate_mesh_data("Island", pts, faces)

    def test_no_paths_or_unsafe_names(self):
        for name in ["../island", "", "1Island", "A" * 64, "Island/part", "Island\n"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    module.validate_mesh_data(name, self.vertices, [[0, 1, 2]])

    def test_curve_dimensions_and_scalar_bounds(self):
        actual = module.validate_curve_data("Island", [self.vertices], True, "2D", 0.04, 0.002, 2)
        self.assertEqual(len(actual[0]), 4)
        for kwargs in [
            ("yes", "2D", 0, 0, 0),
            (True, "4D", 0, 0, 0),
            (True, "2D", -1, 0, 0),
            (True, "2D", 0, 1001, 0),
            (True, "2D", 0, 0, True),
            (True, "2D", 0, 0, 5),
        ]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    module.validate_curve_data("Island", [self.vertices], *kwargs)

    def test_2d_requires_local_plane(self):
        with self.assertRaises(ValueError):
            module.validate_curve_data("Island", [[[0, 0, 1], [1, 0, 1], [1, 1, 1]]], True, "2D", 0, 0, 0)

    def test_json_memory_budget(self):
        with self.assertRaises(ValueError):
            module._budget(["a" * 2000001])

    def _curve_acceptance(self, arguments):
        tools_path = PATH.parent / "skills/blender-data-geometry/tools.yaml"
        tools = json.loads(tools_path.read_text(encoding="utf-8"))["tools"]
        schema = next(tool["input_schema"] for tool in tools if tool["name"] == "create_curve_from_points")
        Draft7Validator.check_schema(schema)
        schema_accepts = Draft7Validator(schema).is_valid(arguments)
        try:
            module.validate_curve_data(
                arguments["name"],
                arguments["splines"],
                arguments.get("closed", True),
                arguments.get("dimensions", "2D"),
                arguments.get("extrude", 0),
                arguments.get("bevel_depth", 0),
                arguments.get("bevel_resolution", 0),
            )
        except ValueError:
            runtime_accepts = False
        else:
            runtime_accepts = True
        return schema_accepts, runtime_accepts

    def test_public_curve_schema_matches_runtime_for_open_closed_and_default(self):
        for dimensions in ("2D", "3D"):
            points = [[0, 0, 0], [1, 0, 0.25 if dimensions == "3D" else 0], [1, 1, 0]]
            for closed in (None, True, False):
                for count in (2, 3):
                    arguments = {"name": "Contour", "splines": [points[:count]], "dimensions": dimensions}
                    if closed is not None:
                        arguments["closed"] = closed
                    expected = count == 3 or closed is False
                    with self.subTest(dimensions=dimensions, closed=closed, point_count=count):
                        self.assertEqual(self._curve_acceptance(arguments), (expected, expected))

    def test_public_curve_schema_preserves_point_and_numeric_bounds(self):
        for changes in (
            {"splines": [[[0, 0, 0]]]},
            {"splines": [[[0, 0, 0], [1000001, 0, 0]]]},
            {"splines": [[[0, 0, 0], [True, 0, 0]]]},
            {"extrude": 1001},
            {"bevel_resolution": True},
        ):
            arguments = {"name": "Contour", "splines": [[[0, 0, 0], [1, 0, 0]]], "closed": False}
            arguments.update(changes)
            with self.subTest(changes=changes):
                self.assertEqual(self._curve_acceptance(arguments), (False, False))


if __name__ == "__main__":
    unittest.main()
