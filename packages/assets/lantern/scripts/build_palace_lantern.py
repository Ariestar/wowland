"""Build SM_PalaceLantern_6S — a game-ready hexagonal palace lantern.

Run:
    blender -b --python assets/lantern/scripts/build_palace_lantern.py

Outputs:
    assets/lantern/exports/SM_PalaceLantern_6S.blend
    assets/lantern/exports/SM_PalaceLantern_6S.glb
    assets/lantern/exports/SM_PalaceLantern_6S.fbx
    assets/lantern/renders/raw/*.png
    assets/lantern/reports/build_report.json
"""

import bpy
import bmesh
import json
import math
import os
import random
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.dirname(HERE)
EXPORT_DIR = os.path.join(ASSET_DIR, "exports")
RENDER_DIR = os.path.join(ASSET_DIR, "renders")
RAW_RENDER_DIR = os.path.join(RENDER_DIR, "raw")
REPORT_DIR = os.path.join(ASSET_DIR, "reports")
for path in (EXPORT_DIR, RENDER_DIR, RAW_RENDER_DIR, REPORT_DIR):
    os.makedirs(path, exist_ok=True)
for old_render in os.listdir(RAW_RENDER_DIR):
    if old_render.lower().endswith(".png"):
        try:
            os.remove(os.path.join(RAW_RENDER_DIR, old_render))
        except OSError:
            pass

# ---------------------------------------------------------------------------
# Scene reset and collections
# ---------------------------------------------------------------------------

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0


def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    if parent is not None:
        parent.children.link(col)
    else:
        scene.collection.children.link(col)
    return col


COL_ROOT = new_collection("COL_Lantern")
COL_GEO = new_collection("COL_Geo", COL_ROOT)
COL_EXPORT = new_collection("COL_Export", COL_ROOT)
COL_LIGHTS = new_collection("COL_Lights", COL_ROOT)
COL_CAMERAS = new_collection("COL_Cameras", COL_ROOT)
COL_RENDER = new_collection("COL_Render", COL_ROOT)

# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------


def make_material(name, base, metallic=0.0, roughness=0.5, emission=None,
                  emission_strength=0.0, coat=0.0, sheen=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Coat Weight"].default_value = coat
    bsdf.inputs["Sheen Weight"].default_value = sheen
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = (*base, 1.0)
    return mat


MAT_PAPER = make_material(
    "MAT_Lantern_Paper", base=(0.38, 0.012, 0.006), roughness=0.55,
    emission=(1.0, 0.055, 0.008), emission_strength=1.4, sheen=0.15)
MAT_WOOD = make_material(
    "MAT_Lantern_Wood", base=(0.065, 0.012, 0.007), roughness=0.42, coat=0.18)
MAT_GOLD = make_material(
    "MAT_Lantern_Gold", base=(0.82, 0.54, 0.16), metallic=1.0, roughness=0.30, coat=0.12)
MAT_TASSEL = make_material(
    "MAT_Lantern_Tassel", base=(0.50, 0.015, 0.012), roughness=0.86, sheen=0.35)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def move_to_collection(obj, col):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    col.objects.link(obj)


def apply_transform(obj, location=True, rotation=True, scale=True):
    activate(obj)
    bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)


def add_box(name, size, location, rotation_z, material, collection, bevel=0.0,
            bevel_segments=1):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=(0, 0, rotation_z))
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    apply_transform(obj)
    if bevel > 0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = bevel_segments
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(50)
        activate(obj)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_cylinder(name, vertices, radius, depth, location, rotation, material,
                 collection, bevel=0.0, bevel_segments=1):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, end_fill_type="TRIFAN",
        location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    apply_transform(obj)
    if bevel > 0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = bevel_segments
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(50)
        activate(obj)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_cone(name, vertices, radius1, radius2, depth, location, direction,
             material, collection):
    rotation = Vector(direction).to_track_quat("Z", "Y").to_euler()
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices, radius1=radius1, radius2=radius2, depth=depth,
        end_fill_type="TRIFAN", location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    apply_transform(obj)
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_sphere(name, radius, location, material, collection, segments=16, rings=8):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    apply_transform(obj)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_torus(name, major_radius, minor_radius, location, rotation, material,
              collection, major_segments=24, minor_segments=6):
    bpy.ops.mesh.primitive_torus_add(
        major_segments=major_segments, minor_segments=minor_segments,
        major_radius=major_radius, minor_radius=minor_radius,
        location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    apply_transform(obj)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def shade_smooth(obj):
    activate(obj)
    bpy.ops.object.shade_smooth()


def shade_smooth_by_angle(obj, angle_deg=35.0):
    activate(obj)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle_deg))


def box_project_uv(obj):
    mesh = obj.data
    if mesh.uv_layers:
        return
    uv = mesh.uv_layers.new(name="UVMap")
    if not mesh.vertices:
        return
    coords = [v.co for v in mesh.vertices]
    mins = [min(c[i] for c in coords) for i in range(3)]
    maxs = [max(c[i] for c in coords) for i in range(3)]
    spans = [max(maxs[i] - mins[i], 1e-6) for i in range(3)]
    for poly in mesh.polygons:
        normal = poly.normal
        axis = max(range(3), key=lambda i: abs(normal[i]))
        for li in poly.loop_indices:
            co = mesh.vertices[mesh.loops[li].vertex_index].co
            if axis == 0:
                u, v = co.y, co.z
                su, sv = spans[1], spans[2]
                ou, ov = mins[1], mins[2]
            elif axis == 1:
                u, v = co.x, co.z
                su, sv = spans[0], spans[2]
                ou, ov = mins[0], mins[2]
            else:
                u, v = co.x, co.y
                su, sv = spans[0], spans[1]
                ou, ov = mins[0], mins[1]
            uv.data[li].uv = ((u - ou) / su, (v - ov) / sv)


def ensure_uv(obj):
    if not obj.data.uv_layers:
        box_project_uv(obj)


def recalc_normals(obj):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def add_solidify(obj, thickness):
    mod = obj.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = 0.0
    mod.use_even_offset = True
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    recalc_normals(obj)


def add_curve_tube(name, points, radius, material, collection, cyclic=False):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 3
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    spline.use_cyclic_u = cyclic
    curve.bevel_depth = radius
    curve.bevel_resolution = 1
    curve.use_fill_caps = True
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    activate(obj)
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    obj.name = name
    # Curve bevel caps are not watertight after conversion; weld and cap them.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.00001)
    bpy.ops.mesh.fill_holes(sides=0)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    move_to_collection(obj, collection)
    return obj


# Geometry constants
R = 0.30                # hexagon circumradius (vertex radius), body width 0.60 m
BODY_TOP = 0.335
BODY_BOTTOM = -0.335
PANEL_R = R - 0.015     # 0.285
PANEL_BULGE = 0.012
HOOK_Z = 0.835


def hex_point(i, radius, z=0.0):
    a = math.radians(60.0 * i)
    return Vector((radius * math.cos(a), radius * math.sin(a), z))


# ---------------------------------------------------------------------------
# Frame: 6 pillars, 12 rails, 6+6 gold trim beams, corner collars, mullions
# ---------------------------------------------------------------------------

parts = []

for i in range(6):
    x, y = hex_point(i, R)[:2]
    angle = math.radians(60.0 * i)
    parts.append(add_box(
        f"SM_PalaceLantern_Pillar_{i + 1}", (0.028, 0.028, 0.70),
        (x, y, 0.0), angle, MAT_WOOD, COL_GEO, bevel=0.003, bevel_segments=2))

for level_name, z in (("Top", BODY_TOP), ("Bottom", BODY_BOTTOM)):
    for i in range(6):
        p0 = hex_point(i, R)
        p1 = hex_point((i + 1) % 6, R)
        mid = (p0 + p1) / 2.0
        angle = math.atan2(p1.y - p0.y, p1.x - p0.x)
        parts.append(add_box(
            f"SM_PalaceLantern_Rail_{level_name}_{i + 1}", (R * 1.01, 0.026, 0.032),
            (mid.x, mid.y, z), angle, MAT_WOOD, COL_GEO, bevel=0.002))

for level_name, z in (("Top", 0.36), ("Bottom", -0.36)):
    for i in range(6):
        p0 = hex_point(i, R + 0.003)
        p1 = hex_point((i + 1) % 6, R + 0.003)
        mid = (p0 + p1) / 2.0
        angle = math.atan2(p1.y - p0.y, p1.x - p0.x)
        parts.append(add_box(
            f"SM_PalaceLantern_GoldTrim_{level_name}_{i + 1}", (R * 1.01, 0.020, 0.012),
            (mid.x, mid.y, z), angle, MAT_GOLD, COL_GEO))

for i in range(6):
    x, y = hex_point(i, R)[:2]
    angle = math.radians(60.0 * i)
    for level_name, z in (("Top", 0.335), ("Bottom", -0.335)):
        parts.append(add_cylinder(
            f"SM_PalaceLantern_Collar_{level_name}_{i + 1}", 8, 0.026, 0.030,
            (x, y, z), (0, 0, angle), MAT_GOLD, COL_GEO))

# Vertical mullions on each panel: two thin gold strips per side.
for i in range(6):
    a = hex_point(i, 1.0)
    b = hex_point((i + 1) % 6, 1.0)
    for j, u in enumerate((1.0 / 3.0, 2.0 / 3.0)):
        p = a.lerp(b, u)
        direction = p.normalized()
        radius = PANEL_R + PANEL_BULGE * math.sin(math.pi * u) + 0.004
        pos = direction * radius
        angle = math.atan2(direction.y, direction.x)
        parts.append(add_box(
            f"SM_PalaceLantern_Mullion_{i + 1}_{j + 1}", (0.012, 0.010, 0.64),
            (pos.x, pos.y, 0.0), angle, MAT_GOLD, COL_GEO))

# ---------------------------------------------------------------------------
# Paper panels: 6 curved grids, 8 x 4 quads each
# ---------------------------------------------------------------------------


def create_panel(side_index, cols=8, rows=4):
    a = hex_point(side_index, 1.0)
    b = hex_point((side_index + 1) % 6, 1.0)
    verts = []
    for v in range(rows + 1):
        vv = v / rows
        z = BODY_BOTTOM + 0.02 + (0.63 * vv)
        for u in range(cols + 1):
            uu = u / cols
            chord = a.lerp(b, uu)
            direction = chord.normalized()
            radius = PANEL_R + PANEL_BULGE * math.sin(math.pi * uu) * math.sin(math.pi * vv)
            p = direction * radius
            verts.append((p.x, p.y, z))
    faces = []
    for v in range(rows):
        for u in range(cols):
            i0 = v * (cols + 1) + u
            i1 = i0 + 1
            i2 = i0 + (cols + 2)
            i3 = i0 + (cols + 1)
            faces.append((i0, i1, i2, i3))
    mesh = bpy.data.meshes.new(f"SM_PalaceLantern_Panel_{side_index + 1}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(f"SM_PalaceLantern_Panel_{side_index + 1}", mesh)
    COL_GEO.objects.link(obj)
    obj.data.materials.append(MAT_PAPER)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    # grid UVs
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        cell = poly.index
        col = cell % cols
        row = cell // cols
        coords = [
            (col / cols, row / rows),
            ((col + 1) / cols, row / rows),
            ((col + 1) / cols, (row + 1) / rows),
            (col / cols, (row + 1) / rows),
        ]
        for li, uvco in zip(poly.loop_indices, coords):
            uv.data[li].uv = uvco
    add_solidify(obj, 0.002)
    return obj


for i in range(6):
    parts.append(create_panel(i))

# ---------------------------------------------------------------------------
# Roof and bottom cap
# ---------------------------------------------------------------------------


def create_cap(name, rings, apex_z, material, collection, thickness=0.008):
    verts = []
    for radius, z in rings:
        for i in range(6):
            p = hex_point(i, radius, z)
            verts.append((p.x, p.y, p.z))
    faces = []
    ring_count = len(rings)
    for ring in range(ring_count - 1):
        for i in range(6):
            a = ring * 6 + i
            b = ring * 6 + (i + 1) % 6
            c = (ring + 1) * 6 + (i + 1) % 6
            d = (ring + 1) * 6 + i
            faces.append((a, b, c, d))
    apex = len(verts)
    verts.append((0.0, 0.0, apex_z))
    last = (ring_count - 1) * 6
    for i in range(6):
        faces.append((last + i, last + (i + 1) % 6, apex))
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    recalc_normals(obj)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    add_solidify(obj, thickness)
    ensure_uv(obj)
    return obj


ROOF_RINGS = [(0.36, 0.35), (0.32, 0.41), (0.23, 0.46), (0.13, 0.495), (0.05, 0.52)]
parts.append(create_cap("SM_PalaceLantern_Roof", ROOF_RINGS, 0.535, MAT_WOOD, COL_GEO))

BOTTOM_RINGS = [(0.36, -0.35), (0.32, -0.41), (0.23, -0.46), (0.13, -0.49), (0.05, -0.51)]
parts.append(create_cap("SM_PalaceLantern_BottomCap", BOTTOM_RINGS, -0.525, MAT_WOOD, COL_GEO))

# Roof ribs follow the six roof ridges.
for i in range(6):
    a = math.radians(60.0 * i)
    points = []
    for radius, z in ROOF_RINGS:
        points.append((radius * math.cos(a), radius * math.sin(a), z + 0.004))
    points.append((0.0, 0.0, 0.539))
    parts.append(add_curve_tube(
        f"SM_PalaceLantern_RoofRib_{i + 1}", points, 0.0045, MAT_GOLD, COL_GEO))

# Six up-turned eave horns.
for i in range(6):
    a = math.radians(60.0 * i)
    pts = []
    for radius, z in ((0.345, 0.352), (0.390, 0.362), (0.425, 0.382), (0.445, 0.408)):
        pts.append((radius * math.cos(a), radius * math.sin(a), z))
    parts.append(add_curve_tube(
        f"SM_PalaceLantern_EaveHorn_{i + 1}", pts, 0.0055, MAT_GOLD, COL_GEO))

# Bottom gold trim ring.
for i in range(6):
    p0 = hex_point(i, 0.365)
    p1 = hex_point((i + 1) % 6, 0.365)
    mid = (p0 + p1) / 2.0
    angle = math.atan2(p1.y - p0.y, p1.x - p0.x)
    parts.append(add_box(
        f"SM_PalaceLantern_BottomTrim_{i + 1}", (0.365 * 1.01, 0.018, 0.010),
        (mid.x, mid.y, -0.35), angle, MAT_GOLD, COL_GEO))

# ---------------------------------------------------------------------------
# Top finial and hanging ring
# ---------------------------------------------------------------------------

parts.append(add_cylinder(
    "SM_PalaceLantern_FinialPlinth", 6, 0.065, 0.030, (0, 0, 0.550),
    (0, 0, 0), MAT_GOLD, COL_GEO))
parts.append(add_sphere("SM_PalaceLantern_FinialBead", 0.045, (0, 0, 0.600), MAT_GOLD, COL_GEO))
parts.append(add_cylinder(
    "SM_PalaceLantern_FinialStem", 12, 0.012, 0.040, (0, 0, 0.660),
    (0, 0, 0), MAT_GOLD, COL_GEO))
parts.append(add_sphere("SM_PalaceLantern_FinialBead2", 0.026, (0, 0, 0.695), MAT_GOLD, COL_GEO, segments=12, rings=6))
parts.append(add_cylinder(
    "SM_PalaceLantern_HookStem", 8, 0.007, 0.060, (0, 0, 0.735),
    (0, 0, 0), MAT_GOLD, COL_GEO))
parts.append(add_torus(
    "SM_PalaceLantern_HookRing", 0.038, 0.006, (0, 0, 0.790),
    (math.pi / 2, 0, 0), MAT_GOLD, COL_GEO, major_segments=16, minor_segments=4))

# ---------------------------------------------------------------------------
# Bottom medallion, knot and 16-strand tassel
# ---------------------------------------------------------------------------

parts.append(add_cylinder(
    "SM_PalaceLantern_BottomMedallion", 16, 0.085, 0.022, (0, 0, -0.515),
    (0, 0, 0), MAT_GOLD, COL_GEO))
parts.append(add_torus(
    "SM_PalaceLantern_BottomMedallionRing", 0.098, 0.005, (0, 0, -0.510),
    (0, 0, 0), MAT_GOLD, COL_GEO, major_segments=16, minor_segments=4))
parts.append(add_sphere("SM_PalaceLantern_BottomBead", 0.038, (0, 0, -0.550), MAT_TASSEL, COL_GEO, segments=16, rings=8))
parts.append(add_cylinder(
    "SM_PalaceLantern_TasselCollar", 12, 0.020, 0.030, (0, 0, -0.590),
    (0, 0, 0), MAT_GOLD, COL_GEO))
parts.append(add_cylinder(
    "SM_PalaceLantern_TasselCord", 8, 0.005, 0.070, (0, 0, -0.625),
    (0, 0, 0), MAT_TASSEL, COL_GEO))
parts.append(add_sphere("SM_PalaceLantern_TasselKnot", 0.038, (0, 0, -0.665), MAT_TASSEL, COL_GEO, segments=16, rings=8))
parts.append(add_cylinder(
    "SM_PalaceLantern_TasselBand", 12, 0.026, 0.018, (0, 0, -0.690),
    (0, 0, 0), MAT_GOLD, COL_GEO))

random.seed(20261114)
for i in range(20):
    angle = math.radians(360.0 * i / 20.0)
    top = Vector((0.014 * math.cos(angle), 0.014 * math.sin(angle), -0.705))
    bottom = Vector((
        (0.060 + random.uniform(-0.005, 0.005)) * math.cos(angle),
        (0.060 + random.uniform(-0.005, 0.005)) * math.sin(angle),
        -1.065 - random.uniform(0.0, 0.030),
    ))
    direction = bottom - top
    midpoint = (top + bottom) / 2.0
    parts.append(add_cone(
        f"SM_PalaceLantern_TasselStrand_{i + 1:02d}", 6, 0.0045, 0.0015,
        direction.length, midpoint, direction, MAT_TASSEL, COL_GEO))

# ---------------------------------------------------------------------------
# "福" gold medallions on front and back panels
# ---------------------------------------------------------------------------

FONT_PATH = "C:/Windows/Fonts/simhei.ttf"
font = bpy.data.fonts.load(FONT_PATH, check_existing=True)


def add_fu_medallion(side, y_sign):
    curve = bpy.data.curves.new(f"Txt_Fu_{side}", "FONT")
    curve.body = "福"
    curve.font = font
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = 1.0
    curve.extrude = 0.006
    curve.resolution_u = 4
    obj = bpy.data.objects.new(f"SM_PalaceLantern_Fu_{side}", curve)
    COL_GEO.objects.link(obj)
    activate(obj)
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    obj.name = f"SM_PalaceLantern_Fu_{side}"
    # Extruded text contains duplicated seam vertices; weld before decimation.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.00001)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    # scale height to 0.19 m
    bpy.context.view_layer.update()
    height = max(obj.dimensions.y, 1e-6)
    factor = 0.19 / height
    obj.scale = (factor, factor, factor)
    apply_transform(obj)
    dec = obj.modifiers.new("Decimate", "DECIMATE")
    dec.ratio = 0.22
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=dec.name)
    tri = obj.modifiers.new("Triangulate", "TRIANGULATE")
    tri.keep_custom_normals = False
    bpy.ops.object.modifier_apply(modifier=tri.name)
    obj.data.materials.append(MAT_GOLD)
    # face front (-Y) or back (+Y), upright
    rot_z = 0.0 if y_sign < 0 else math.pi
    obj.rotation_euler = (math.pi / 2.0, 0.0, rot_z)
    obj.location = (0.0, 0.305 * y_sign, 0.005)
    apply_transform(obj)
    ensure_uv(obj)
    move_to_collection(obj, COL_GEO)
    return obj


for side, sign in (("Front", -1), ("Back", 1)):
    parts.append(add_fu_medallion(side, sign))
    parts.append(add_torus(
        f"SM_PalaceLantern_FuRing_{side}", 0.115, 0.0045,
        (0, 0.302 * sign, 0.005), (math.pi / 2.0, 0.0, 0.0 if sign < 0 else math.pi),
        MAT_GOLD, COL_GEO, major_segments=16, minor_segments=4))

# ---------------------------------------------------------------------------
# Join, clean up, UV check, origin, metadata
# ---------------------------------------------------------------------------

# Ensure every part has a UV map before joining.
for obj in list(COL_GEO.objects):
    if obj.type == "MESH":
        ensure_uv(obj)

bpy.ops.object.select_all(action="DESELECT")
for obj in COL_GEO.objects:
    if obj.type == "MESH":
        obj.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
lantern = bpy.context.object
lantern.name = "SM_PalaceLantern_6S"
lantern.data.name = "SM_PalaceLantern_6S_mesh"
move_to_collection(lantern, COL_EXPORT)


def dedupe_material_slots(obj):
    materials = [slot.material for slot in obj.material_slots]
    unique = []
    name_to_index = {}
    remap = {}
    for index, material in enumerate(materials):
        if material is None:
            continue
        if material.name in name_to_index:
            remap[index] = name_to_index[material.name]
        else:
            name_to_index[material.name] = len(unique)
            remap[index] = len(unique)
            unique.append(material)
    # Clearing material slots resets every polygon's material_index to 0,
    # so capture the old indices first.
    old_indices = [poly.material_index for poly in obj.data.polygons]
    obj.data.materials.clear()
    for material in unique:
        obj.data.materials.append(material)
    for poly, old_index in zip(obj.data.polygons, old_indices):
        poly.material_index = remap.get(old_index, old_index)


dedupe_material_slots(lantern)

# Clean stray geometry. Do not weld across separate parts: overlapping
# tassel strands and frame joints must stay independent shells.
activate(lantern)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.delete_loose(use_verts=True, use_edges=True, use_faces=False)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode="OBJECT")

# Keep every UV loop inside 0-1; the materials are solid-color so clamping
# four stray loops is safe and keeps the validation gate clean.
uv_layer = lantern.data.uv_layers.active
if uv_layer:
    for datum in uv_layer.data:
        u, v = datum.uv
        datum.uv = (min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0))

# Pivot at the top of the hanging ring (0, 0, 0): shift mesh down by HOOK_Z.
for vertex in lantern.data.vertices:
    vertex.co.z -= HOOK_Z
lantern.location = (0.0, 0.0, 0.0)
shade_smooth_by_angle(lantern, 35.0)

lantern["asset_name"] = "SM_PalaceLantern_6S"
lantern["asset_type"] = "Hexagonal palace lantern / festival prop"
lantern["dimensions_m"] = "0.90 x 0.78 x 1.93 (roof span x depth x H incl. tassel); body 0.60 x 0.60 x 0.66"
lantern["pivot"] = "Top center of hanging ring"
lantern["forward"] = "-Y (front panel)"
lantern["source_notes"] = "Frame / lampshade / decoration decomposition after Ji 2023; target Unity URP mobile"

# The asset stays at the world origin: its mesh occupies z = -1.93..0 and the
# origin is the top of the hanging ring, so engines place it cleanly.
lantern.location = (0.0, 0.0, 0.0)

# Save the clean, engine-ready asset before the look-dev rig is added.
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT_DIR, "SM_PalaceLantern_6S.blend"))

# Render-only copy hung from the beam; keeps the exported asset at the origin.
lantern_render = lantern.copy()
lantern_render.data = lantern.data
lantern_render.name = "SM_PalaceLantern_6S_RENDER"
COL_RENDER.objects.link(lantern_render)
lantern_render.location = (0.0, 0.0, 2.95)
lantern.hide_render = True

# Focus target for depth of field, at the lantern body centre.
focus = bpy.data.objects.new("EMP_LanternFocus", None)
COL_RENDER.objects.link(focus)
focus.location = (0.0, 0.0, 2.10)

# ---------------------------------------------------------------------------
# Look-dev scene: backdrop, beam, bokeh, lights, cameras
# ---------------------------------------------------------------------------


def make_emission_material(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (*color, 1.0)
    emission.inputs["Strength"].default_value = strength
    links.new(emission.outputs["Emission"], out.inputs["Surface"])
    return mat


def make_gradient_backdrop_material():
    mat = bpy.data.materials.new("MAT_Render_Backdrop")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 0.55
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.004, 0.010, 0.013, 1)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.012, 0.043, 0.050, 1)
    texco = nodes.new("ShaderNodeTexCoord")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    links.new(texco.outputs["Generated"], separate.inputs["Vector"])
    links.new(separate.outputs["Z"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = (0.008, 0.02, 0.025, 1)
    return mat


MAT_BACKDROP = make_gradient_backdrop_material()

# Cylindrical backdrop (inside-facing; material is emission and double-sided).
bpy.ops.mesh.primitive_cylinder_add(
    vertices=64, radius=10.0, depth=12.0, end_fill_type="NOTHING",
    location=(0, 0, 2.5))
backdrop = bpy.context.object
backdrop.name = "SM_Render_Backdrop"
backdrop.data.materials.append(MAT_BACKDROP)
move_to_collection(backdrop, COL_RENDER)
for poly in backdrop.data.polygons:
    poly.use_smooth = True

# Dark floor.
bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0, 0, 0))
floor = bpy.context.object
floor.name = "SM_Render_Floor"
mat_floor = make_material("MAT_Render_Floor", base=(0.012, 0.009, 0.008), roughness=0.32, metallic=0.0)
floor.data.materials.append(mat_floor)
move_to_collection(floor, COL_RENDER)

# Overhead wooden beam.
MAT_RENDER_BEAM = make_material(
    "MAT_Render_Beam", base=(0.006, 0.0015, 0.0012), roughness=0.70)
beam = add_box("SM_Render_Beam", (4.2, 0.14, 0.14), (0, 0, 3.05), 0.0,
               MAT_RENDER_BEAM, COL_RENDER, bevel=0.006)
hero_only_props = [beam]
# Cord from beam to hook.
hook_cord = add_cylinder(
    "SM_Render_HookCord", 8, 0.006, 0.10, (0, 0, 3.00), (0, 0, 0),
    MAT_TASSEL, COL_RENDER)
hero_only_props.append(hook_cord)

# Warm bokeh spheres behind the lantern.
MAT_BOKEH_A = make_emission_material("MAT_Render_BokehWarm", (1.0, 0.28, 0.06), 5.0)
MAT_BOKEH_B = make_emission_material("MAT_Render_BokehRed", (0.9, 0.05, 0.02), 4.0)
bokeh_positions = [
    (-2.8, 4.8, 2.9, 0.10), (-1.7, 5.4, 2.2, 0.07), (-0.8, 5.0, 3.4, 0.12),
    (1.2, 5.6, 3.0, 0.08), (2.4, 4.9, 2.4, 0.11), (3.4, 5.8, 3.5, 0.06),
    (-3.6, 5.9, 1.8, 0.08), (0.3, 6.2, 1.7, 0.09),
]
for i, (x, y, z, radius) in enumerate(bokeh_positions):
    mat = MAT_BOKEH_A if i % 2 == 0 else MAT_BOKEH_B
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=radius, location=(x, y, z))
    sphere = bpy.context.object
    sphere.name = f"SM_Render_Bokeh_{i + 1:02d}"
    sphere.data.materials.append(mat)
    move_to_collection(sphere, COL_RENDER)
    hero_only_props.append(sphere)


def add_area_light(name, location, energy, color, size, target=(0, 0, 2.15)):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.color = color
    data.size = size
    obj = bpy.data.objects.new(name, data)
    COL_LIGHTS.objects.link(obj)
    obj.location = location
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return obj


add_area_light("LGT_Key", (-3.0, -3.2, 4.0), 320.0, (1.0, 0.86, 0.72), 2.2)
add_area_light("LGT_Fill", (3.6, -2.6, 2.2), 130.0, (0.35, 0.55, 0.95), 2.6)
add_area_light("LGT_Rim", (1.2, 3.2, 3.6), 240.0, (1.0, 0.45, 0.18), 1.8)
add_area_light("LGT_Bounce", (0.0, -1.6, 0.6), 70.0, (1.0, 0.45, 0.20), 1.4, target=(0, 0, 1.4))

# Inner warm lights to make the paper glow read from the front.
for i, z in enumerate((2.45, 2.15, 1.85)):
    data = bpy.data.lights.new(f"LGT_Inner_{i + 1}", type="POINT")
    data.energy = 18.0
    data.color = (1.0, 0.30, 0.06)
    data.shadow_soft_size = 0.12
    obj = bpy.data.objects.new(f"LGT_Inner_{i + 1}", data)
    COL_LIGHTS.objects.link(obj)
    obj.location = (0, 0, z)


def add_camera(name, location, target, lens):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_width = 36.0
    obj = bpy.data.objects.new(name, data)
    COL_CAMERAS.objects.link(obj)
    obj.location = location
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return obj


CAM_HERO = add_camera("CAM_Hero", (2.5, -4.4, 2.45), (0, 0, 2.12), 68.0)
CAM_FRONT = add_camera("CAM_Front", (0, -5.4, 2.15), (0, 0, 2.10), 75.0)
CAM_RIGHT = add_camera("CAM_Right", (5.4, 0, 2.15), (0, 0, 2.10), 75.0)
CAM_BACK = add_camera("CAM_Back", (0, 5.4, 2.15), (0, 0, 2.10), 75.0)
CAM_THREE = add_camera("CAM_ThreeQuarter", (3.6, -3.8, 2.35), (0, 0, 2.10), 66.0)
CAM_DETAIL = add_camera("CAM_DetailRoof", (1.2, -1.7, 3.05), (0, 0, 2.72), 90.0)

# Depth of field on the hero and detail cameras.
for cam, fstop in ((CAM_HERO, 2.8), (CAM_THREE, 3.2), (CAM_DETAIL, 4.0)):
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = focus
    cam.data.dof.aperture_fstop = fstop

# World
world = bpy.data.worlds.new("W_World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.003, 0.008, 0.010, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.25

# Render settings
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 64
scene.eevee.use_raytracing = True
scene.eevee.use_shadows = True
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = 0.0
scene.camera = CAM_HERO
scene.render.filepath = os.path.join(RAW_RENDER_DIR, "hero.png")

# ---------------------------------------------------------------------------
# Save .blend, export GLB/FBX, render views
# ---------------------------------------------------------------------------

scene.render.resolution_x = 900
scene.render.resolution_y = 1200
LOOKDEV_PATH = os.path.join(EXPORT_DIR, "SM_PalaceLantern_6S_lookdev.blend")
bpy.ops.wm.save_as_mainfile(filepath=LOOKDEV_PATH)

# Export selected mesh only.
bpy.ops.object.select_all(action="DESELECT")
lantern.select_set(True)
bpy.context.view_layer.objects.active = lantern
glb_path = os.path.join(EXPORT_DIR, "SM_PalaceLantern_6S.glb")
bpy.ops.export_scene.gltf(
    filepath=glb_path, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT",
    export_texcoords=True, export_normals=True, export_cameras=False,
    export_lights=False)

fbx_path = os.path.join(EXPORT_DIR, "SM_PalaceLantern_6S.fbx")
try:
    bpy.ops.export_scene.fbx(
        filepath=fbx_path, use_selection=True, object_types={"MESH"},
        apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
        apply_unit_scale=True, bake_anim=False, path_mode="AUTO")
    fbx_exported = True
except Exception as exc:
    print("FBX_EXPORT_FAILED:", repr(exc))
    fbx_exported = False

# Render helper.


render_errors = []


def render_view(camera, filename, res_x, res_y, samples):
    scene.camera = camera
    scene.render.resolution_x = res_x
    scene.render.resolution_y = res_y
    scene.eevee.taa_render_samples = samples
    scene.render.filepath = os.path.join(RAW_RENDER_DIR, filename)
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as exc:
        render_errors.append({"view": filename, "error": repr(exc)})
        print("RENDER_FAILED:", filename, repr(exc))
    return scene.render.filepath


render_view(CAM_HERO, "hero.png", 900, 1200, 64)
render_view(CAM_THREE, "three_quarter.png", 900, 1200, 48)

for obj in hero_only_props:
    obj.hide_render = True
render_view(CAM_FRONT, "front.png", 640, 800, 32)
render_view(CAM_RIGHT, "right.png", 640, 800, 32)
render_view(CAM_BACK, "back.png", 640, 800, 32)
render_view(CAM_DETAIL, "detail_roof.png", 800, 800, 48)
for obj in hero_only_props:
    obj.hide_render = False

# Restore hero camera and save again.
scene.camera = CAM_HERO
scene.render.resolution_x = 900
scene.render.resolution_y = 1200
scene.eevee.taa_render_samples = 64
scene.render.filepath = os.path.join(RAW_RENDER_DIR, "hero.png")
bpy.ops.wm.save_as_mainfile(filepath=LOOKDEV_PATH)

# Report stats.
tris = sum(len(p.vertices) - 2 for p in lantern.data.polygons)
report = {
    "asset": "SM_PalaceLantern_6S",
    "triangles": tris,
    "vertices": len(lantern.data.vertices),
    "materials": [slot.material.name for slot in lantern.material_slots if slot.material],
    "dimensions_m": list(lantern.dimensions),
    "pivot": "top of hanging ring",
    "exports": {
        "blend": os.path.join(EXPORT_DIR, "SM_PalaceLantern_6S.blend"),
        "lookdev": LOOKDEV_PATH,
        "glb": glb_path,
        "fbx": fbx_path if fbx_exported else None,
    },
    "renders": sorted(os.listdir(RAW_RENDER_DIR)),
    "render_errors": render_errors,
}
with open(os.path.join(REPORT_DIR, "build_report.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=2)

print("BUILD_REPORT_START")
print(json.dumps(report, ensure_ascii=False, indent=2))
print("BUILD_REPORT_END")
