"""Unit tests for :func:`dcc_mcp_blender._scene_ops.parent_object`.

These tests use a fake ``bpy`` that models the two Blender behaviours the fix
depends on:

* a world matrix evaluated as ``parent.matrix_world @ matrix_parent_inverse @
  matrix_basis``;
* a **cached** evaluated matrix (``ob->obmat``) that only refreshes on a
  depsgraph update, so reading ``matrix_world`` right after a move returns the
  previous transform. That cache is what silently dropped re-parented objects
  at their parent's origin.
"""

from __future__ import annotations

from tests.conftest import load_and_call, make_mock_bpy


class FakeMatrix:
    """Minimal 4x4 matrix supporting the operations used while parenting."""

    def __init__(self, rows):
        self.rows = [[float(value) for value in row] for row in rows]

    # ── constructors ────────────────────────────────────────────────────────
    @classmethod
    def identity(cls) -> "FakeMatrix":
        return cls([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])

    @classmethod
    def translation(cls, x: float, y: float, z: float) -> "FakeMatrix":
        matrix = cls.identity()
        matrix.rows[0][3] = float(x)
        matrix.rows[1][3] = float(y)
        matrix.rows[2][3] = float(z)
        return matrix

    # ── mathutils-like API ──────────────────────────────────────────────────
    def copy(self) -> "FakeMatrix":
        return FakeMatrix(self.rows)

    def __iter__(self):
        return iter([list(row) for row in self.rows])

    def __getitem__(self, index):
        return list(self.rows[index])

    def __matmul__(self, other: "FakeMatrix") -> "FakeMatrix":
        rows = []
        for i in range(4):
            rows.append([sum(self.rows[i][k] * other.rows[k][j] for k in range(4)) for j in range(4)])
        return FakeMatrix(rows)

    def inverted(self) -> "FakeMatrix":
        """Gauss-Jordan inverse; raises ``ValueError`` for singular matrices."""
        size = 4
        aug = [list(self.rows[i]) + [1.0 if j == i else 0.0 for j in range(size)] for i in range(size)]
        for col in range(size):
            pivot = max(range(col, size), key=lambda row: abs(aug[row][col]))
            if abs(aug[pivot][col]) < 1e-12:
                raise ValueError("matrix is singular")
            aug[col], aug[pivot] = aug[pivot], aug[col]
            pivot_value = aug[col][col]
            aug[col] = [value / pivot_value for value in aug[col]]
            for row in range(size):
                if row == col:
                    continue
                factor = aug[row][col]
                if factor:
                    aug[row] = [value - factor * pivot_row for value, pivot_row in zip(aug[row], aug[col])]
        return FakeMatrix([row[size:] for row in aug])


class FakeTransformObject:
    """Object whose ``matrix_world`` is cached until the depsgraph is flushed."""

    def __init__(self, name: str, obj_type: str = "EMPTY", basis: FakeMatrix | None = None):
        self.name = name
        self.type = obj_type
        self.data = None
        self.parent = None
        self.matrix_parent_inverse = FakeMatrix.identity()
        self.world_assignments = 0
        self._basis = basis or FakeMatrix.identity()
        self._cached_world = FakeMatrix.identity()

    # ── transform channels ──────────────────────────────────────────────────
    @property
    def matrix_basis(self) -> FakeMatrix:
        return self._basis.copy()

    @property
    def location(self) -> list:
        """Local translation channel: the translation column of the basis."""
        return [self._basis.rows[0][3], self._basis.rows[1][3], self._basis.rows[2][3]]

    @location.setter
    def location(self, value) -> None:
        x, y, z = (float(component) for component in value)
        # Mirrors Blender: assigning the channel rewrites the basis in place and
        # leaves the rotation/scale part of the basis untouched.
        for row, component in zip(range(3), (x, y, z)):
            self._basis.rows[row][3] = component

    def _compute_world(self) -> FakeMatrix:
        if self.parent is None:
            return self._basis.copy()
        return self.parent.matrix_world @ self.matrix_parent_inverse @ self._basis

    def flush(self) -> None:
        """Recompute the cached evaluated matrix (parents first)."""
        if self.parent is not None:
            self.parent.flush()
        self._cached_world = self._compute_world()

    @property
    def matrix_world(self) -> FakeMatrix:
        # Blender returns the last evaluated matrix, not a live computation.
        return self._cached_world.copy()

    @matrix_world.setter
    def matrix_world(self, value: FakeMatrix) -> None:
        # Mirrors BKE_object_apply_mat4(): solve matrix_basis for the parent
        # chain, keeping matrix_parent_inverse untouched.
        self.world_assignments += 1
        local = value.copy()
        if self.parent is not None:
            local = self.parent.matrix_world.inverted() @ local
            local = self.matrix_parent_inverse.inverted() @ local
        self._basis = local
        self.location = [local.rows[0][3], local.rows[1][3], local.rows[2][3]]


class SingularMatrix(FakeMatrix):
    """Matrix that cannot be inverted — models a zero-scale ``matrix_basis``."""

    def inverted(self) -> "FakeMatrix":
        raise ValueError("matrix does not have an inverse")


class ZeroScaleObject(FakeTransformObject):
    """Object whose ``matrix_basis`` has no inverse, like a zero-scale object."""

    @property
    def matrix_basis(self) -> SingularMatrix:
        return SingularMatrix(self._basis.rows)


class FakeViewLayer:
    def __init__(self, objects):
        self._objects = objects
        self.update_calls = 0

    def update(self):
        self.update_calls += 1
        for obj in self._objects:
            obj.flush()


def _bpy_for_transform_objects(objects):
    bpy = make_mock_bpy()
    lookup = {obj.name: obj for obj in objects}
    bpy.data.objects.get.side_effect = lambda name: lookup.get(name)
    bpy.context.view_layer = FakeViewLayer(objects)
    return bpy


def _world_translation(obj) -> list:
    rows = list(obj.matrix_world)
    return [rows[0][3], rows[1][3], rows[2][3]]


def _call_parent(bpy, child_name: str, parent_name=None) -> dict:
    kwargs = {"child_name": child_name}
    if parent_name is not None:
        kwargs["parent_name"] = parent_name
    return load_and_call("blender-objects/scripts/parent_object.py", bpy, **kwargs)


def _call_move(bpy, object_name: str, location) -> dict:
    return load_and_call("blender-objects/scripts/move_object.py", bpy, name=object_name, location=location)


class TestParentObjectPreservesWorldTransform:
    """Regression tests for the "move first, parent second" flow."""

    def test_parent_after_move_keeps_the_world_transform(self):
        pivot = FakeTransformObject("Pivot")
        camera = FakeTransformObject("HeroCam", "CAMERA")
        bpy = _bpy_for_transform_objects([pivot, camera])

        # move_object sets the basis; the depsgraph is NOT flushed afterwards,
        # exactly like a background Blender session. The test asserts against
        # the transform that was actually applied, not against the stale
        # cached matrix that a matrix_world read would return here.
        placed_world = [6.4, 0.0, 2.35]
        camera.matrix_world = FakeMatrix.translation(*placed_world)

        result = _call_parent(bpy, "HeroCam", "Pivot")

        assert result["success"] is True, result
        assert result["context"]["world_transform_preserved"] is True
        assert result["context"]["parent_name"] == "Pivot"
        camera.flush()
        assert _world_translation(camera) == placed_world
        # The local transform channels the caller set are still in place, so a
        # get_object_info read-back is meaningful too.
        assert camera.location == [6.4, 0.0, 2.35]

    def test_parent_under_a_transformed_parent_keeps_the_world_transform(self):
        pivot = FakeTransformObject("Pivot", basis=FakeMatrix.translation(2.0, 3.0, 4.0))
        child = FakeTransformObject("HeroCam", "CAMERA", basis=FakeMatrix.translation(6.4, 0.0, 2.35))
        bpy = _bpy_for_transform_objects([pivot, child])
        pivot.flush()
        child.flush()
        # Parenting must NOT drag the child to the parent's space: with an
        # identity matrix_parent_inverse it would jump to (8.4, 3.0, 6.35).
        expected_world = [6.4, 0.0, 2.35]

        result = _call_parent(bpy, "HeroCam", "Pivot")

        assert result["success"] is True, result
        assert result["context"]["world_transform_preserved"] is True
        child.flush()
        assert _world_translation(child) == expected_world
        # Two depsgraph evaluations: one before capturing the world transform,
        # one before verifying it. The parenting itself needs no evaluation
        # because matrix_basis is recomputed from the local channels on read.
        assert bpy.context.view_layer.update_calls == 2
        # matrix_parent_inverse compensates for the parent, while the local
        # transform channels stay exactly as the caller left them.
        assert [row[3] for row in child.matrix_parent_inverse][:3] == [-2.0, -3.0, -4.0]
        assert [row[3] for row in child.matrix_basis][:3] == [6.4, 0.0, 2.35]

    def test_parent_then_move_still_applies_local_transforms(self):
        """The existing correct ordering must not regress."""
        pivot = FakeTransformObject("Pivot")
        camera = FakeTransformObject("HeroCam", "CAMERA")
        bpy = _bpy_for_transform_objects([pivot, camera])

        assert _call_parent(bpy, "HeroCam", "Pivot")["success"] is True

        moved = _call_move(bpy, "HeroCam", [1.0, 2.0, 3.0])
        assert moved["success"] is True, moved
        assert moved["context"]["location"] == [1.0, 2.0, 3.0]

        # Parent sits at the origin, so local and world translations match.
        camera.flush()
        assert _world_translation(camera) == [1.0, 2.0, 3.0]
        assert camera.location == [1.0, 2.0, 3.0]

    def test_move_after_parenting_keeps_targeting_world_coordinates(self):
        """parent_object cancels the parent, so move_object targets world space.

        matrix_parent_inverse is solved as ``P⁻¹ @ W @ B⁻¹``; for a child that
        was unparented when it was parented that collapses to ``P⁻¹``, so the
        local translation channel keeps reading back as the world position.
        """
        pivot = FakeTransformObject("Pivot", basis=FakeMatrix.translation(2.0, 3.0, 4.0))
        camera = FakeTransformObject("HeroCam", "CAMERA")
        bpy = _bpy_for_transform_objects([pivot, camera])
        camera.flush()

        assert _call_parent(bpy, "HeroCam", "Pivot")["success"] is True
        assert _call_move(bpy, "HeroCam", [1.0, 2.0, 3.0])["success"] is True

        camera.flush()
        # World coordinates, not the parent-space offset (3.0, 5.0, 7.0) that a
        # bake-into-basis (parentinv = I) implementation would produce.
        assert _world_translation(camera) == [1.0, 2.0, 3.0]
        assert camera.location == [1.0, 2.0, 3.0]

    def test_unparent_keeps_the_world_transform(self):
        pivot = FakeTransformObject("Pivot", basis=FakeMatrix.translation(5.0, 0.0, 0.0))
        child = FakeTransformObject("HeroCam", "CAMERA", basis=FakeMatrix.translation(1.0, 2.0, 3.0))
        child.parent = pivot
        child.matrix_parent_inverse = FakeMatrix.identity()
        bpy = _bpy_for_transform_objects([pivot, child])
        pivot.flush()
        child.flush()
        expected_world = [6.0, 2.0, 3.0]

        result = _call_parent(bpy, "HeroCam")

        assert result["success"] is True, result
        assert result["context"]["world_transform_preserved"] is True
        assert result["context"]["parent_name"] is None
        assert child.parent is None
        child.flush()
        assert _world_translation(child) == expected_world

    def test_failed_transform_recovery_is_reported_instead_of_silent_success(self):
        class IgnoringParentInverseObject(FakeTransformObject):
            """A Blender that ignores matrix_parent_inverse when evaluating."""

            def _compute_world(self):
                if self.parent is None:
                    return self._basis.copy()
                return self.parent.matrix_world @ self._basis

        pivot = IgnoringParentInverseObject("Pivot", basis=FakeMatrix.translation(2.0, 3.0, 4.0))
        child = IgnoringParentInverseObject("HeroCam", "CAMERA", basis=FakeMatrix.translation(6.4, 0.0, 2.35))
        bpy = _bpy_for_transform_objects([pivot, child])
        pivot.flush()
        child.flush()

        result = _call_parent(bpy, "HeroCam", "Pivot")

        assert result["success"] is False
        assert "world transform was not preserved" in result["message"]
        assert result["context"]["world_transform_preserved"] is False
        assert result["context"]["world_transform_delta"] > 1e-6
        assert result["context"]["child_name"] == "HeroCam"

    def test_reparenting_directly_to_another_parent_keeps_the_world_transform(self):
        """Switching A -> B without unparenting first must not drop the child."""
        first_parent = FakeTransformObject("RigA", basis=FakeMatrix.translation(2.0, 3.0, 4.0))
        second_parent = FakeTransformObject("RigB", basis=FakeMatrix.translation(-1.0, 0.5, 10.0))
        child = FakeTransformObject("HeroCam", "CAMERA", basis=FakeMatrix.translation(6.4, 0.0, 2.35))
        bpy = _bpy_for_transform_objects([first_parent, second_parent, child])
        first_parent.flush()
        second_parent.flush()
        child.flush()
        expected_world = [6.4, 0.0, 2.35]

        assert _call_parent(bpy, "HeroCam", "RigA")["success"] is True
        result = _call_parent(bpy, "HeroCam", "RigB")

        assert result["success"] is True, result
        assert result["context"]["world_transform_preserved"] is True
        assert result["context"]["parent_name"] == "RigB"
        assert child.parent is second_parent
        child.flush()
        assert _world_translation(child) == expected_world
        # The inverse of the new parent replaced the inverse of the old one.
        assert [row[3] for row in child.matrix_parent_inverse][:3] == [1.0, -0.5, -10.0]

    def test_zero_scale_basis_falls_back_to_assigning_the_world_matrix(self):
        """An un-invertible basis takes the fallback, which still preserves world."""
        parent = FakeTransformObject("Pivot", basis=FakeMatrix.translation(2.0, 3.0, 4.0))
        child = ZeroScaleObject("HeroCam", "CAMERA", basis=FakeMatrix.translation(6.4, 0.0, 2.35))
        bpy = _bpy_for_transform_objects([parent, child])
        parent.flush()
        child.flush()
        expected_world = [6.4, 0.0, 2.35]

        result = _call_parent(bpy, "HeroCam", "Pivot")

        assert result["success"] is True, result
        assert result["context"]["world_transform_preserved"] is True
        # The un-invertible basis sent _keep_world_transform down its fallback,
        # which bakes the parent transform into the local channels instead.
        assert child.world_assignments == 1
        child.flush()
        assert _world_translation(child) == expected_world

    def test_missing_objects_and_self_parenting_still_report_errors(self):
        pivot = FakeTransformObject("Pivot")
        bpy = _bpy_for_transform_objects([pivot])

        missing = _call_parent(bpy, "Ghost", "Pivot")
        assert missing["success"] is False
        assert missing["message"] == "Object not found: Ghost"

        self_parent = _call_parent(bpy, "Pivot", "Pivot")
        assert self_parent["success"] is False
        assert self_parent["message"] == "Invalid parent"
