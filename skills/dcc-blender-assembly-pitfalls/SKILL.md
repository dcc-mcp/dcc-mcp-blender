---
name: dcc-blender-assembly-pitfalls
description: |-
  Read this BEFORE writing any Blender geometry code through MCP, whenever you
  are about to (1) create or size mesh primitives - bpy.ops.mesh.primitive_cube_add,
  primitive_cylinder_add, primitive_uv_sphere_add, primitive_cone_add - or set
  scale / dimensions on a part; (2) orient a part with rotation_euler or
  rotation_quaternion, or aim a shaft, bolt, post, limb, or pipe along a
  direction; or (3) place two or more parts so they touch, join, boolean, or
  export as one object. Also read it when an assembled model renders with
  visible seams, falls apart under a boolean, or comes back the wrong size.
license: MIT
allowed-tools: Read Bash
metadata:
  dcc-mcp:
    dcc: blender
    layer: operator
    stage: authoring
    version: "1.0.0"
    tags: [blender, assembly, geometry, pitfalls, modeling, verification]
    search-hint: "parts do not line up, model exploded, seam between parts, wrong size, cylinder faces wrong way, boolean failed, scale is half"
    search-aliases: [assembly, pitfall, gap, overlap, joint, connection map, primitive size, euler axis, apply scale, export scale]
    intent: "Prevent the three geometric failures that silently ruin MCP-authored Blender assemblies, and force a connection map before any geometry is written."
---

# Blender assembly pitfalls

This is a **failure-mode skill**, not a tool catalog. Every number below was
measured on Blender 4.5.13 LTS (`daeeeca98fb0`) in a headless
`blender --background --factory-startup` session. If a claim here cannot be
reproduced, the claim is wrong - fix the skill, do not work around the symptom.

Read it when you are about to create, size, orient, or join geometry. Skip it
for read-only scene inspection.

The failure this skill prevents always has the same shape: **the code runs, no
exception is raised, the viewport looks plausible, and the model is wrong.**
Nothing in Blender warns you. So the defence is not "be careful" - it is the
Phase 1 connection map and the Phase 3 checklist at the end.

---

## Pitfall 1 - `size` is a full edge, `radius` is a half edge, and `scale=` halves your intent

### The trap

`primitive_cube_add(size=N)` makes a cube **N across**, centred on the origin,
so its vertices sit at +/- N/2. Cylinders, spheres, and cones take `radius`,
which is **half** the extent. A request for "0.4" therefore produces a 0.4
*half-extent* for a cube and a 0.4 *full extent* for a sphere. Same number,
2x different object.

### Measured

| Call | World extent X | What the request actually gave |
|---|---|---|
| `primitive_cube_add(size=1.0)` | 1.0 | vertices at **+/-0.5**, not +/-1.0 |
| same cube, then `scale = (0.4, 0.4, 0.4)` | 0.4 | **half-extent 0.2**, not 0.4 |
| `primitive_cube_add(size=0.8)` | 0.8 | half-extent **0.4** - the intended result |
| `primitive_uv_sphere_add(radius=0.5)` | **1.0** | radius is a half extent |
| `primitive_cylinder_add(radius=0.5, depth=1.0)` | **1.0** | radius is a half extent |
| `primitive_cone_add(radius1=0.5, radius2=0, depth=1.0)` | **1.0** | radius is a half extent |
| `primitive_cube_add(size=0.5)` | **0.5** | size is a full extent |

The `scale = 0.4` row is the one that costs hours: `cube.dimensions` afterwards
reads `(0.4, 0.4, 0.4)`, so a model that verifies its work by reading
`dimensions` sees the number it asked for and reports success - while the part
is half the size it needs to be. `dimensions` is the **full** extent; a mating
calculation needs the **half** extent.

### Measured bonus - primitives spawn at the 3D cursor

With `scene.cursor.location = (7, 8, 9)`, a bare
`bpy.ops.mesh.primitive_cube_add(size=1.0)` with no `location=` argument
created the cube at **(7.0, 8.0, 9.0)**, not at the origin. Any earlier
operator that moved the cursor silently relocates every later part.

### The rule

1. Size primitives with the operator's own argument, never with `scale=`.
   Non-uniform boxes are the one exception, and they must be followed by
   `bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)`.
2. Always pass `location=` explicitly.
3. When a dimension comes from a spec, write the unit into the variable name
   (`plate_x_m`, `post_len_mm`) and convert in one place.
4. Verify with the **world bounding box**, never with `dimensions` alone - see
   Phase 3.

---

## Pitfall 2 - Euler orientation picks the wrong axis, or is silently discarded

### The trap

A cylinder is built along its local **+Z**. To re-aim it you must rotate about
X or Y. Rotating about Z can never change a Z axis, so
`rotation_euler = (0, 0, 90 degrees)` is a **no-op on the axis**: the part still
points up, and every joint measured off it is 90 degrees wrong.

### Measured - local +Z in world space after each assignment

| `rotation_euler` (XYZ order) | Resulting axis | Verdict |
|---|---|---|
| `(0, 0, 0)` | `(0, 0, 1)` | unchanged |
| `(0, 0, 90 deg)` | `(0, 0, 1)` | **no effect on the axis** - the classic wrong guess |
| `(90 deg, 0, 0)` | `(0, -1, 0)` | points **-Y**, not +X |
| `(0, 90 deg, 0)` | `(1, 0, 0)` | points **+X** - the only correct answer of the three |

### Measured - the silent-discard variant

`object.rotation_euler` and `object.rotation_quaternion` are two views of one
rotation, and **only the one matching `rotation_mode` is read**. Writing the
other one is accepted, stored, and ignored.

- `rotation_mode = "QUATERNION"`, then `rotation_euler = (0, 0, 0)` -> the axis
  **stayed at `(1, 0, 0)`**. Reading `rotation_euler` back returned `(0, 0, 0)`.
- `rotation_mode = "XYZ"`, then `rotation_quaternion = (0.7071, 0.7071, 0, 0)`
  -> the axis **stayed at `(0, 0, 1)`**. Reading `rotation_euler` back returned
  `(0, 0, 0)`.

In both cases the value you wrote is the value that reads back, so a self-check
that compares `rotation_euler` against the intent passes while the object is
misaligned.

### The rule

1. Set `obj.rotation_mode = "XYZ"` first, then assign `rotation_euler`.
2. Never derive an orientation by guessing; derive it once and reuse the table
   above: aim +X -> `(0, 90 deg, 0)`, aim +Y -> `(-90 deg, 0, 0)`, aim +Z ->
   `(0, 0, 0)`.
3. Verify the **resulting axis**, not the Euler tuple:
   `obj.matrix_world.to_3x3().normalized() @ Vector((0, 0, 1))` must equal the
   declared aim vector.

---

## Pitfall 3 - "touching" is not "joined": zero overlap is a broken assembly

### The trap

Placing part B so its face is exactly flush with part A's face produces **zero
interpenetration**. It looks correct in the viewport and is wrong in every
downstream operation: a boolean union over coplanar faces produces
non-manifold or empty results, the shared faces z-fight in the render, a rigid
body simulation lets the parts drift apart, and a 3D print has zero wall
thickness at the joint.

### Measured

- Two 0.1 m cubes placed face to face: the measured gap between `A.max.x` and
  `B.min.x` was **0.000000 m**. Flush, not joined.
- Repositioned with an explicit overlap: measured **0.005000 m**.

At model scale this is the difference between a seam you can see in the render
and a joint you cannot. The failure is invisible in wireframe and unavoidable
in the render.

### The rule

Every joint needs a target overlap written down **before** the geometry exists.
A workable default:

> target overlap = **25% of the thinner part's extent along the joint axis**,
> never less than 1 mm, and never zero.

### Measured corollary - `dimensions` includes modifiers but ignores rotation

This asymmetry is what makes flush-placement bugs so hard to spot:

| Situation | `obj.dimensions` | True world AABB |
|---|---|---|
| 0.1 m cube + Array (count 6, offset 1.5x) | `(0.85, 0.1, 0.1)` | `(0.85, 0.1, 0.1)` - modifiers **are** included |
| 0.1 m cube + Solidify (thickness 0.02, offset 1) | `(0.123094, ...)` | `(0.123094, ...)` - modifiers **are** included |
| cube scaled `(4, 1, 1)`, then rotated 90 deg about Y | `(4.0, 1.0, 1.0)` | **`(1.0, 1.0, 4.0)`** - rotation is **not** |

So a placement computed from `dimensions` is correct before a rotation and
**3 m wrong on a 4 m part** after one. The result is identical with or without
applied scale. Always place and verify from the world bounding box.

### Measured corollary - export units are a separate axis of failure

`scene.unit_settings.length_unit` (`METERS` / `CENTIMETERS` / `MILLIMETERS`) is
**display only**: changing it left `scale_length` at 1.0 and left `dimensions`
at `(2.0, 2.0, 2.0)`. But `scale_length` is **not** display only - it is
applied on export:

- `scale_length = 1.0` -> a 1-unit cube exported to FBX and re-imported measured
  **1.000000**.
- `scale_length = 0.01` -> the same cube measured **0.010000**, **100x too
  small**, with no warning at export time.

Check `scale_length == 1.0` before every FBX / OBJ / USD export unless the
target engine's unit convention is explicitly known.

---

## Phase 1 - the connection map (do this before any geometry code)

Fill this in **first**. If a joint is not in the table, its part does not get
built yet. Every row must carry a target overlap; a row with a blank overlap is
a joint that will be flush, and flush is broken.

Overlap convention, stated once so it is mechanically checkable:

> **Axis** is the single world axis the joint closes along.
> **Contact face** is `min` or `max` - which extreme of the *fixed* part, along
> that axis, the joint closes against.
> **Mating face** is `min` or `max` - which extreme of the *moving* part ends up
> **inside** the fixed part.
> **Overlap** = `abs(contact-face coordinate - mating-face coordinate)` along
> the axis, and it only counts when the mating face is on the interior side.

### Template

| Joint | Moving part | Fixed part | Axis | Fixed contact face | Moving mating face | Target overlap |
|---|---|---|---|---|---|---|
| J1 |             |            | X/Y/Z | min / max          | min / max          | ___ m / ___ mm  |
| J2 |             |            | X/Y/Z | min / max          | min / max          | ___ m / ___ mm  |
| J3 |             |            | X/Y/Z | min / max          | min / max          | ___ m / ___ mm  |

### Worked example - a 4-part rig, verified on Blender 4.5.13

Parts (authored in mm, built in metres): `base_plate` 120x120x12 mm box;
`post` r=12 mm, h=160 mm cylinder; `arm` r=10 mm, l=100 mm cylinder aimed at
world +X; `knob` r=18 mm sphere.

| Joint | Moving part | Fixed part | Axis | Fixed contact face | Moving mating face | Target overlap |
|---|---|---|---|---|---|---|
| J1 | post       | base_plate | Z | max (plate top)  | min (post bottom) | 6 mm  |
| J2 | arm        | post       | X | min (post -X)    | min (arm -X cap)  | 8 mm  |
| J3 | knob       | arm        | X | max (arm +X cap) | min (knob -X)     | 10 mm |

Aim vectors, declared with the parts so Pitfall 2 cannot be guessed at:

```text
base_plate -> (0, 0, 1)    post -> (0, 0, 1)
arm        -> (1, 0, 0)    knob  -> (0, 0, 1)
```

J2 is the row that matters: the arm must be aimed with `(0, 90 deg, 0)`. Aimed
with `(0, 0, 90 deg)` instead it stays vertical, and the overlap on J2 and J3
is zero no matter how carefully the coordinates are computed.

---

## Phase 2 - build rules

1. Create every part at the origin, oriented, with `location=` passed
   explicitly (Pitfall 1) and `rotation_mode` set before `rotation_euler`
   (Pitfall 2).
2. Size with the operator argument, not with `scale=`. If `scale=` is
   unavoidable, apply it immediately.
3. Place parts from the connection map, in joint order, recomputing the world
   bounds of the fixed part after each placement. Never place from a hard-coded
   coordinate that "looks right".
4. Re-read the world bounding box after every placement - `dimensions` lies
   about rotation.

---

## Phase 3 - verification checklist

Mechanically checkable. Every item has a pass/fail rule and a tolerance. Run
the script below; do not eyeball it.

| # | Check | Pass rule | Catches |
|---|---|---|---|
| 1 | Overlap per joint | `measured >= target - 1 um` **and** the mating face is on the interior side | Pitfall 3, flush joints |
| 2 | Orientation per part | angle between local +Z and the declared aim `< 0.001 deg` | Pitfall 2, wrong axis and silent discard |
| 3 | World bounding box per part | `0 < size < 1.0 m` for desk-scale objects, no NaN | Pitfall 1 halving, 100x unit errors |
| 4 | Normals per part | signed mesh volume `> 0` (outward normals) | inverted normals, failed booleans |
| 5 | Applied scale per part | `scale == (1, 1, 1)` | non-uniform scale surviving to export |
| 6 | Modifier count per part | `== 0` before export | geometry that differs from what was verified |
| 7 | Export units | `scene.unit_settings.scale_length == 1.0` | the 100x FBX error |

Tolerance note: check 1 uses **1 micron**. Float noise on a 0.008 m target is
around 1e-9 m, but a hard `>=` comparison still fails on the last bit - use the
tolerance, not an exact comparison.

### Runnable verification

Save as `verify_assembly.py` and run it with the target Blender:

```bash
blender --background --factory-startup --python verify_assembly.py
```

It rebuilds the worked example from the connection map and prints a PASS/FAIL
line per check. The exit code is non-zero if anything fails.

```python
"""Verify a Blender assembly against its connection map. Blender 4.5+."""

import json
import math
import sys

import bpy
from mathutils import Vector

MM = 0.001
# 1 micron: below this is float noise, not geometry.
TOLERANCE_M = 1e-6

# joint, moving part, fixed part, axis, fixed contact face, moving mating face, target overlap
CONNECTION_MAP = [
    ("J1", "post", "base_plate", "Z", "max", "min", 6 * MM),
    ("J2", "arm", "post", "X", "min", "min", 8 * MM),
    ("J3", "knob", "arm", "X", "max", "min", 10 * MM),
]
PARTS = {
    "base_plate": ("cube", {"x": 120 * MM, "y": 120 * MM, "z": 12 * MM}),
    "post": ("cylinder", {"radius": 12 * MM, "height": 160 * MM}),
    "arm": ("cylinder", {"radius": 10 * MM, "height": 100 * MM}),
    "knob": ("sphere", {"radius": 18 * MM}),
}
# Which world axis each part's local +Z must aim along.
AIM = {"base_plate": (0, 0, 1), "post": (0, 0, 1), "arm": (1, 0, 0), "knob": (0, 0, 1)}
# Derived, never guessed. Rotating about Z cannot re-aim a Z axis.
EULER_FOR_AIM = {(0, 0, 1): (0.0, 0.0, 0.0), (1, 0, 0): (0.0, math.radians(90.0), 0.0)}
AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    unit = bpy.context.scene.unit_settings
    unit.system, unit.length_unit, unit.scale_length = "METRIC", "METERS", 1.0


def world_bounds(obj):
    pts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return [min(v[i] for v in pts) for i in range(3)], [max(v[i] for v in pts) for i in range(3)]


def build(kind, spec):
    # Pitfall 1: cube takes a FULL edge length, sphere/cylinder take a RADIUS.
    if kind == "cube":
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
        obj = bpy.context.active_object
        obj.scale = (spec["x"], spec["y"], spec["z"])
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    elif kind == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(radius=spec["radius"], depth=spec["height"], location=(0, 0, 0))
        obj = bpy.context.active_object
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=spec["radius"], location=(0, 0, 0))
        obj = bpy.context.active_object
    obj.name = obj.data.name = kind
    return obj


def orient(obj, aim):
    # Pitfall 2: rotation_mode first. rotation_euler is discarded in QUATERNION mode.
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = EULER_FOR_AIM[aim]
    bpy.context.view_layer.update()


def build_assembly():
    clear_scene()
    objects = {name: build(kind, spec) for name, (kind, spec) in PARTS.items()}
    for name, obj in objects.items():
        orient(obj, AIM[name])

    objects["base_plate"].location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    plate_top = world_bounds(objects["base_plate"])[1][2]

    post_height = PARTS["post"][1]["height"]
    objects["post"].location = (0.0, 0.0, plate_top - CONNECTION_MAP[0][6] + post_height / 2.0)
    bpy.context.view_layer.update()
    post_min, post_max = world_bounds(objects["post"])

    arm_len = PARTS["arm"][1]["height"]
    arm_axis_z = post_max[2] - 10 * MM
    objects["arm"].location = (post_min[0] + CONNECTION_MAP[1][6] + arm_len / 2.0, 0.0, arm_axis_z)
    bpy.context.view_layer.update()
    arm_plus_x_cap = world_bounds(objects["arm"])[1][0]

    knob_r = PARTS["knob"][1]["radius"]
    objects["knob"].location = (arm_plus_x_cap - CONNECTION_MAP[2][6] + knob_r, 0.0, arm_axis_z)
    bpy.context.view_layer.update()
    return objects


def verify(objects):
    checks = []

    for joint, moving, fixed, axis, fixed_face, moving_face, target in CONNECTION_MAP:
        i = AXIS_INDEX[axis]
        m_min, m_max = world_bounds(objects[moving])
        f_min, f_max = world_bounds(objects[fixed])
        f_coord = f_max[i] if fixed_face == "max" else f_min[i]
        m_coord = m_max[i] if moving_face == "max" else m_min[i]
        # Interior side: against a "max" face the mating face must be <=,
        # against a "min" face it must be >=.
        sign = -1.0 if fixed_face == "max" else 1.0
        inside = (m_coord - f_coord) * sign >= -TOLERANCE_M
        overlap = abs(f_coord - m_coord)
        checks.append((
            "overlap_" + joint,
            "%s.%s -> %s.%s along %s" % (moving, moving_face, fixed, fixed_face, axis),
            round(target, 6), round(overlap, 6),
            "PASS" if inside and overlap >= target - TOLERANCE_M else "FAIL",
        ))

    for name, aim in AIM.items():
        axis = objects[name].matrix_world.to_3x3().normalized() @ Vector((0, 0, 1))
        err = math.degrees(axis.angle(Vector(aim)))
        checks.append((
            "orientation_" + name, "local +Z must aim at %s" % (aim,),
            0.0, round(err, 6), "PASS" if err < 0.001 else "FAIL",
        ))

    for name, obj in objects.items():
        lo, hi = world_bounds(obj)
        size = [round(hi[i] - lo[i], 6) for i in range(3)]
        checks.append((
            "world_bounds_" + name, "size x/y/z in metres", "0 < s < 1.0", size,
            "PASS" if all(0.0 < s < 1.0 for s in size) else "FAIL",
        ))

    for name, obj in objects.items():
        mesh = obj.data
        volume = sum(
            Vector(mesh.vertices[f.vertices[0]].co).dot(
                Vector(mesh.vertices[f.vertices[1]].co).cross(Vector(mesh.vertices[f.vertices[2]].co))
            ) / 6.0
            for f in mesh.polygons
        )
        checks.append((
            "normals_" + name, "signed volume > 0 (outward normals)", "> 0",
            round(volume, 9), "PASS" if volume > 0 else "FAIL",
        ))
        checks.append((
            "applied_scale_" + name, "scale == (1,1,1) before export", [1.0, 1.0, 1.0],
            [round(s, 6) for s in obj.scale],
            "PASS" if all(abs(abs(s) - 1.0) < 1e-6 for s in obj.scale) else "FAIL",
        ))
        checks.append((
            "modifiers_" + name, "modifier count == 0 before export", 0,
            len(obj.modifiers), "PASS" if not obj.modifiers else "FAIL",
        ))

    scale_length = bpy.context.scene.unit_settings.scale_length
    checks.append((
        "export_units", "scale_length == 1.0", 1.0, scale_length,
        "PASS" if abs(scale_length - 1.0) < 1e-9 else "FAIL",
    ))
    return checks


def main():
    checks = verify(build_assembly())
    keys = ("check", "detail", "target", "measured", "status")
    print("===VERIFY-BEGIN===")
    print(json.dumps([dict(zip(keys, c)) for c in checks], indent=2))
    print("===VERIFY-END===")
    failed = [c for c in checks if c[4] == "FAIL"]
    for name, detail, target, measured, _ in failed:
        print("FAIL %s: %s (target %s, measured %s)" % (name, detail, target, measured))
    print("%d checks, %d failed" % (len(checks), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

Verified output on Blender 4.5.13 LTS, 24 checks, 0 failed (exit code 0):

```text
overlap_J1   post.min -> base_plate.max along Z   target 0.006  measured 0.006  PASS
overlap_J2   arm.min  -> post.min along X         target 0.008  measured 0.008  PASS
overlap_J3   knob.min -> arm.max along X          target 0.01   measured 0.01   PASS

orientation_base_plate / post / arm / knob   target 0.0 deg   measured 0.0 deg   PASS

world_bounds_base_plate  [0.12, 0.12, 0.012]
world_bounds_post        [0.024, 0.024, 0.16]
world_bounds_arm         [0.1, 0.02, 0.02]
world_bounds_knob        [0.036, 0.036, 0.036]

normals_base_plate   volume 8.64e-05   PASS      applied_scale_base_plate  [1, 1, 1]  PASS
normals_post         volume 2.4001e-05  PASS     applied_scale_post        [1, 1, 1]  PASS
normals_arm          volume 1.0417e-05  PASS     applied_scale_arm         [1, 1, 1]  PASS
normals_knob         volume 1.2251e-05  PASS     applied_scale_knob        [1, 1, 1]  PASS

modifiers_base_plate / post / arm / knob   0      PASS
export_units         scale_length 1.0        PASS
```

---

## Adapting this skill to another DCC

Only the measurement tables are Blender-specific. The three-phase shape -
connection map before geometry, mechanical verification after - ports to Maya,
Houdini, and 3ds Max unchanged. When porting, re-measure every number on the
target host; do not carry the values across.
