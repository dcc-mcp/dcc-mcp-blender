"""Unit tests for blender-expressions skill scripts (bpy mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


def _make_driver_var(name="var"):
    var = MagicMock()
    var.name = name
    target = MagicMock()
    target.id_type = "OBJECT"
    target.data_path = ""
    target.bone_target = ""
    var.targets = [target]
    var.type = "SINGLE_PROP"
    return var


def _make_fcurve(data_path="location.x", array_index=0, expression="0"):
    driver = MagicMock()
    driver.type = "SCRIPTED"
    driver.expression = expression
    driver.use_self = False
    driver.is_valid = True
    driver.variables = MagicMock()
    driver.variables.__iter__ = MagicMock(return_value=iter([]))

    fcurve = MagicMock()
    fcurve.data_path = data_path
    fcurve.array_index = array_index
    fcurve.driver = driver
    fcurve.evaluate = MagicMock(return_value=0.0)
    return fcurve


def _make_obj_with_driver(name="Cube", data_path="location.x"):
    fcurve = _make_fcurve(data_path=data_path)
    anim_data = MagicMock()
    anim_data.drivers = [fcurve]

    obj = MagicMock()
    obj.name = name
    obj.animation_data = anim_data
    return obj, fcurve


def _bpy_with_obj(obj):
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj
    bpy.data.objects.__iter__ = MagicMock(return_value=iter([obj]))
    return bpy


class TestAddDriver:
    def test_adds_scripted_driver(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.name = "Cube"
        obj.animation_data = None
        bpy.data.objects.get.return_value = obj

        new_fcurve = _make_fcurve()
        obj.driver_add.return_value = new_fcurve

        result = load_and_call(
            "blender-expressions/scripts/add_driver.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
            driver_type="SCRIPTED",
            expression="sin(frame)",
        )

        assert result["success"] is True
        obj.driver_add.assert_called_once_with("location.x", 0)
        assert new_fcurve.driver.expression == "sin(frame)"

    def test_invalid_driver_type_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = MagicMock(name="Cube", animation_data=None)

        result = load_and_call(
            "blender-expressions/scripts/add_driver.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
            driver_type="INVALID",
        )

        assert result["success"] is False

    def test_missing_object_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None

        result = load_and_call(
            "blender-expressions/scripts/add_driver.py",
            bpy,
            object_name="Missing",
            data_path="location.x",
        )

        assert result["success"] is False
        assert "not found" in result["message"].lower()


class TestSetDriverExpression:
    def test_updates_expression_on_existing_driver(self):
        obj, fcurve = _make_obj_with_driver()
        bpy = _bpy_with_obj(obj)

        result = load_and_call(
            "blender-expressions/scripts/set_driver_expression.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
            expression="cos(frame * 0.1)",
        )

        assert result["success"] is True
        assert fcurve.driver.expression == "cos(frame * 0.1)"

    def test_driver_not_found_returns_error(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.name = "Cube"
        obj.animation_data = MagicMock()
        obj.animation_data.drivers = []
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-expressions/scripts/set_driver_expression.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
            expression="1.0",
        )

        assert result["success"] is False

    def test_updates_driver_type_and_use_self(self):
        obj, fcurve = _make_obj_with_driver()
        bpy = _bpy_with_obj(obj)

        result = load_and_call(
            "blender-expressions/scripts/set_driver_expression.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
            expression="sum(v.co.x for v in self.data.vertices)",
            driver_type="SCRIPTED",
            use_self=True,
        )

        assert result["success"] is True
        assert fcurve.driver.use_self is True


class TestRemoveDriver:
    def test_removes_existing_driver(self):
        obj, _fcurve = _make_obj_with_driver()
        bpy = _bpy_with_obj(obj)

        result = load_and_call(
            "blender-expressions/scripts/remove_driver.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
        )

        assert result["success"] is True
        obj.driver_remove.assert_called_once_with("location.x", 0)

    def test_no_animation_data_returns_error(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.name = "Cube"
        obj.animation_data = None
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-expressions/scripts/remove_driver.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
        )

        assert result["success"] is False


class TestListDrivers:
    def test_lists_drivers_on_object(self):
        obj, _fcurve = _make_obj_with_driver(data_path="location.x")
        bpy = _bpy_with_obj(obj)

        result = load_and_call(
            "blender-expressions/scripts/list_drivers.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["drivers"][0]["data_path"] == "location.x"

    def test_lists_all_drivers_when_no_object_specified(self):
        obj, _fcurve = _make_obj_with_driver(data_path="scale.z")
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = obj
        bpy.data.objects.__iter__ = MagicMock(return_value=iter([obj]))

        result = load_and_call("blender-expressions/scripts/list_drivers.py", bpy)

        assert result["success"] is True
        assert result["context"]["count"] >= 1

    def test_object_without_animation_data_returns_empty(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.name = "Cube"
        obj.animation_data = None
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-expressions/scripts/list_drivers.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is True
        assert result["context"]["count"] == 0


class TestAddDriverVariable:
    def test_adds_single_prop_variable(self):
        obj, fcurve = _make_obj_with_driver()
        bpy = _bpy_with_obj(obj)

        new_var = _make_driver_var("my_var")
        fcurve.driver.variables.new.return_value = new_var

        result = load_and_call(
            "blender-expressions/scripts/add_driver_variable.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
            variable_name="my_var",
            variable_type="SINGLE_PROP",
            target_data_path="location.x",
        )

        assert result["success"] is True
        fcurve.driver.variables.new.assert_called_once()

    def test_invalid_variable_type_returns_error(self):
        obj, _fcurve = _make_obj_with_driver()
        bpy = _bpy_with_obj(obj)

        result = load_and_call(
            "blender-expressions/scripts/add_driver_variable.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
            variable_name="bad",
            variable_type="INVALID_TYPE",
        )

        assert result["success"] is False


class TestRemoveDriverVariable:
    def test_removes_existing_variable(self):
        obj, fcurve = _make_obj_with_driver()
        bpy = _bpy_with_obj(obj)

        existing_var = _make_driver_var("my_var")
        fcurve.driver.variables.get = MagicMock(return_value=existing_var)

        result = load_and_call(
            "blender-expressions/scripts/remove_driver_variable.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
            variable_name="my_var",
        )

        assert result["success"] is True
        fcurve.driver.variables.remove.assert_called_once_with(existing_var)

    def test_missing_variable_returns_error(self):
        obj, fcurve = _make_obj_with_driver()
        bpy = _bpy_with_obj(obj)
        fcurve.driver.variables.get = MagicMock(return_value=None)

        result = load_and_call(
            "blender-expressions/scripts/remove_driver_variable.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
            variable_name="no_such",
        )

        assert result["success"] is False


class TestEvaluateDriverExpression:
    def test_evaluates_driver_at_current_frame(self):
        obj, fcurve = _make_obj_with_driver()
        fcurve.evaluate.return_value = 3.14
        bpy = _bpy_with_obj(obj)
        bpy.context.scene.frame_current = 10

        result = load_and_call(
            "blender-expressions/scripts/evaluate_driver_expression.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
        )

        assert result["success"] is True
        assert result["context"]["value"] == 3.14
        assert result["context"]["frame"] == 10.0

    def test_driver_not_found_returns_error(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.name = "Cube"
        obj.animation_data = MagicMock()
        obj.animation_data.drivers = []
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-expressions/scripts/evaluate_driver_expression.py",
            bpy,
            object_name="Cube",
            data_path="location.x",
        )

        assert result["success"] is False
