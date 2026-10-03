"""Pure input-contract tests; actual Blender acceptance has separate receipts."""

import importlib.util
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
