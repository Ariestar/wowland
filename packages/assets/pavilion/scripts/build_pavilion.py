"""Build SM_Env_Pavilion_Hex_01 — a game-ready hexagonal Chinese pavilion.

Run:
    blender -b --python assets/pavilion/scripts/build_pavilion.py

Outputs:
    assets/pavilion/exports/SM_Env_Pavilion_Hex_01.blend
    assets/pavilion/exports/SM_Env_Pavilion_Hex_01_lookdev.blend
    assets/pavilion/exports/SM_Env_Pavilion_Hex_01.glb
    assets/pavilion/exports/SM_Env_Pavilion_Hex_01.fbx
    assets/pavilion/renders/raw/*.png
    assets/pavilion/reports/build_report.json
"""

import bpy
import bmesh
import json
import math
import os
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


COL_ROOT = new_collection("COL_Pavilion")
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


MAT_STONE = make_material("MAT_Pavilion_Stone", base=(0.115, 0.125, 0.14), roughness=0.78)
MAT_WOOD = make_material("MAT_Pavilion_Wood", base=(0.235, 0.018, 0.010), roughness=0.40, coat=0.20)
MAT_GOLD = make_material("MAT_Pavilion_Gold", base=(0.82, 0.54, 0.16), metallic=1.0, roughness=0.30, coat=0.12)
MAT_ROOF = make_material("MAT_Pavilion_Roof", base=(0.018, 0.030, 0.045), metallic=0.15, roughness=0.32, coat=0.25)
MAT_LANTERN = make_material(
    "MAT_Pavilion_Lantern", base=(0.36, 0.012, 0.006), roughness=0.55,
    emission=(1.0, 0.07, 0.010), emission_strength=1.2, sheen=0.15)
MAT_PAINT = make_material("MAT_Pavilion_Paint", base=(0.018, 0.075, 0.085), roughness=0.44, coat=0.10)

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


def add_tapered_column(name, p0, p1, radius_bottom, radius_top, material,
                       collection, vertices=12):
    """Tapered column between two points (Chinese yingzhu taper)."""
    a, b = Vector(p0), Vector(p1)
    delta = b - a
    length = max(delta.length, 1e-6)
    rotation = delta.to_track_quat("Z", "Y").to_euler()
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices, radius1=radius_bottom, radius2=radius_top,
        depth=length, end_fill_type="TRIFAN", location=(a + b) / 2.0,
        rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    apply_transform(obj)
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_disc(name, radius, depth, location, direction, material, collection,
             vertices=12):
    """A shallow cylinder whose axis follows `direction` (eave tile cap)."""
    rotation = Vector(direction).to_track_quat("Z", "Y").to_euler()
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, end_fill_type="TRIFAN",
        location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    apply_transform(obj)
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_sphere(name, radius, location, material, collection, segments=16, rings=8,
               scale=None):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    if scale is not None:
        obj.scale = scale
    apply_transform(obj)
    for poly in obj.data.polygons:
        poly.use_smooth = True
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


def add_bar(name, p0, p1, thickness, material, collection, bevel=0.0):
    """A square bar from p0 to p1; local Z follows the segment."""
    a, b = Vector(p0), Vector(p1)
    delta = b - a
    length = max(delta.length, 1e-6)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(a + b) / 2.0)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (thickness, thickness, length)
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    apply_transform(obj)
    if bevel > 0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 1
        mod.limit_method = "ANGLE"
        activate(obj)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_torus(name, major_radius, minor_radius, location, rotation, material,
              collection, major_segments=16, minor_segments=4):
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


def add_mesh_object(name, verts, faces, material, collection):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    recalc_normals(obj)
    return obj


def recalc_normals(obj):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def add_solidify(obj, thickness, offset=0.0):
    mod = obj.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = offset
    mod.use_even_offset = True
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    recalc_normals(obj)


def add_curve_tube(name, points, radius, material, collection, cyclic=False,
                   resolution_u=3, bevel_resolution=1):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution_u
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    spline.use_cyclic_u = cyclic
    curve.bevel_depth = radius
    curve.bevel_resolution = bevel_resolution
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


def shade_smooth_by_angle(obj, angle_deg=35.0):
    activate(obj)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle_deg))


# ---------------------------------------------------------------------------
# Geometry constants
# ---------------------------------------------------------------------------

R_COL = 1.85
COL_TOP = 3.01
FLOOR_Z = 0.46
EAVE_R = 2.65
EAVE_Z = 3.33
APEX_Z = 4.66
CORNER_LIFT = 0.26
ROOF_THK = 0.07
HEX_SIDE = R_COL  # side length of a regular hexagon equals its circumradius


def hex_point(i, radius, z=0.0):
    angle = math.radians(60.0 * i)
    return Vector((radius * math.cos(angle), radius * math.sin(angle), z))


def add_hex_prism(name, radius, z0, z1, material, collection, bevel=0.0):
    verts = []
    for i in range(6):
        p = hex_point(i, radius)
        verts.append((p.x, p.y, z0))
    for i in range(6):
        p = hex_point(i, radius)
        verts.append((p.x, p.y, z1))
    bottom_center = len(verts)
    verts.append((0.0, 0.0, z0))
    top_center = len(verts)
    verts.append((0.0, 0.0, z1))
    faces = []
    for i in range(6):
        j = (i + 1) % 6
        faces.append((i, j, 6 + j, 6 + i))
        faces.append((bottom_center, j, i))
        faces.append((top_center, 6 + i, 6 + j))
    obj = add_mesh_object(name, verts, faces, material, collection)
    if bevel > 0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 1
        mod.limit_method = "ANGLE"
        activate(obj)
        bpy.ops.object.modifier_apply(modifier=mod.name)
        recalc_normals(obj)
    ensure_uv(obj)
    return obj


# ---------------------------------------------------------------------------
# Podium, floor and steps
# ---------------------------------------------------------------------------

# Sumeru-style podium: projecting lower plinth, recessed waist, upper plinth.
add_hex_prism("SM_Pavilion_Plinth_Lower", 2.62, 0.00, 0.16, MAT_STONE, COL_GEO, bevel=0.014)
add_hex_prism("SM_Pavilion_Plinth_Waist", 2.46, 0.16, 0.30, MAT_STONE, COL_GEO, bevel=0.010)
add_hex_prism("SM_Pavilion_Plinth_Upper", 2.56, 0.30, 0.40, MAT_STONE, COL_GEO, bevel=0.012)
add_hex_prism("SM_Pavilion_Floor", 2.20, 0.40, FLOOR_Z, MAT_WOOD, COL_GEO, bevel=0.008)

# Raised stone panels on the six waist faces (reads as carved relief at game scale).
for i in range(6):
    mid_angle = math.radians(60.0 * i + 30.0)
    mid_radius = 2.46 * math.cos(math.radians(30.0))
    px = math.cos(mid_angle) * (mid_radius + 0.018)
    py = math.sin(mid_angle) * (mid_radius + 0.018)
    add_box(f"SM_Pavilion_PlinthPanel_{i + 1:02d}",
            (2.46 * 0.64, 0.035, 0.085), (px, py, 0.23),
            math.radians(60.0 * i + 120.0), MAT_STONE, COL_GEO, bevel=0.010)

# Four front steps with sloped side slabs (chuidai stone).
step_specs = [(0.345, -2.36), (0.23, -2.74), (0.115, -3.12)]
for index, (height, y) in enumerate(step_specs, start=1):
    add_box(f"SM_Pavilion_Step_{index:02d}", (1.70, 0.38, height),
            (0.0, y, height / 2.0), 0.0, MAT_STONE, COL_GEO, bevel=0.012)
for side in (-1, 1):
    add_bar(f"SM_Pavilion_StepCheek_{'L' if side < 0 else 'R'}",
            (side * 0.93, -2.18, 0.53), (side * 0.93, -3.32, 0.09),
            0.14, MAT_STONE, COL_GEO, bevel=0.010)

# Gold inlay ring around the wooden floor edge.
for i in range(6):
    p0 = hex_point(i, 2.18, FLOOR_Z + 0.008)
    p1 = hex_point((i + 1) % 6, 2.18, FLOOR_Z + 0.008)
    add_curve_tube(f"SM_Pavilion_FloorTrim_{i + 1:02d}", [p0, p1], 0.012,
                   MAT_GOLD, COL_GEO)

# ---------------------------------------------------------------------------
# Columns and column bases
# ---------------------------------------------------------------------------

for i in range(6):
    p = hex_point(i, R_COL)
    p_top = hex_point(i, R_COL - 0.018)
    angle = math.radians(60.0 * i)
    # Square stone plinth + drum-shaped base (gujing).
    add_box(f"SM_Pavilion_ColumnPlinth_{i + 1:02d}", (0.44, 0.44, 0.06),
            (p.x, p.y, FLOOR_Z + 0.03), angle, MAT_STONE, COL_GEO, bevel=0.010)
    add_cylinder(f"SM_Pavilion_ColumnBase_{i + 1:02d}", 8, 0.205, 0.10,
                 (p.x, p.y, FLOOR_Z + 0.11), (0, 0, angle), MAT_STONE, COL_GEO,
                 bevel=0.008)
    # Slight taper and lean-in (cejiao) read as a traditional timber column.
    add_tapered_column(f"SM_Pavilion_Column_{i + 1:02d}",
                       (p.x, p.y, FLOOR_Z + 0.16),
                       (p_top.x, p_top.y, COL_TOP),
                       0.125, 0.102, MAT_WOOD, COL_GEO)
    # Gold bands at foot and head, plus a carved capital block.
    add_cylinder(f"SM_Pavilion_ColumnBandLow_{i + 1:02d}", 12, 0.129, 0.028,
                 (p.x, p.y, FLOOR_Z + 0.20), (0, 0, angle), MAT_GOLD, COL_GEO)
    add_cylinder(f"SM_Pavilion_ColumnBandHigh_{i + 1:02d}", 12, 0.108, 0.028,
                 (p_top.x, p_top.y, COL_TOP - 0.12), (0, 0, angle), MAT_GOLD, COL_GEO)
    add_cylinder(f"SM_Pavilion_ColumnCapital_{i + 1:02d}", 8, 0.155, 0.085,
                 (p_top.x, p_top.y, COL_TOP - 0.045), (0, 0, angle), MAT_WOOD,
                 COL_GEO, bevel=0.006)
    add_cylinder(f"SM_Pavilion_ColumnCapitalRing_{i + 1:02d}", 8, 0.162, 0.022,
                 (p_top.x, p_top.y, COL_TOP - 0.095), (0, 0, angle), MAT_GOLD,
                 COL_GEO)

# ---------------------------------------------------------------------------
# Beam rings, brackets and eave fascia
# ---------------------------------------------------------------------------

for i in range(6):
    p0 = hex_point(i, R_COL)
    p1 = hex_point((i + 1) % 6, R_COL)
    mid = (p0 + p1) / 2.0
    outward = mid.normalized()
    angle = math.atan2(p1.y - p0.y, p1.x - p0.x)
    add_box(f"SM_Pavilion_Beam_{i + 1:02d}", (HEX_SIDE * 1.01, 0.16, 0.20),
            (mid.x, mid.y, COL_TOP), angle, MAT_WOOD, COL_GEO, bevel=0.010)
    # Flat plate beam above the architrave.
    add_box(f"SM_Pavilion_PlateBeam_{i + 1:02d}", (HEX_SIDE * 1.02, 0.24, 0.05),
            (mid.x, mid.y, COL_TOP + 0.145), angle, MAT_WOOD, COL_GEO, bevel=0.008)
    # Lower architrave (xiaoe fang) under the main beam.
    add_box(f"SM_Pavilion_LowerBeam_{i + 1:02d}", (HEX_SIDE * 0.99, 0.12, 0.13),
            (mid.x, mid.y, COL_TOP - 0.46), angle, MAT_WOOD, COL_GEO, bevel=0.008)
    # Painted panel with gold borders on the outward face (caihua accent).
    panel_pos = mid + outward * 0.088
    add_box(f"SM_Pavilion_BeamPanel_{i + 1:02d}", (HEX_SIDE * 0.74, 0.012, 0.11),
            (panel_pos.x, panel_pos.y, COL_TOP), angle, MAT_PAINT, COL_GEO)
    for tag, z in (("Low", COL_TOP - 0.075), ("High", COL_TOP + 0.075)):
        trim_pos = mid + outward * 0.095
        add_box(f"SM_Pavilion_BeamPanelTrim{tag}_{i + 1:02d}",
                (HEX_SIDE * 0.80, 0.018, 0.018),
                (trim_pos.x, trim_pos.y, z), angle, MAT_GOLD, COL_GEO)
    add_box(f"SM_Pavilion_BeamTrim_{i + 1:02d}", (HEX_SIDE * 1.02, 0.025, 0.035),
            (mid.x, mid.y, COL_TOP + 0.115), angle, MAT_GOLD, COL_GEO)
    # Eave fascia follows the roof edge; gold drip edge below it.
    q0 = hex_point(i, EAVE_R - 0.02)
    q1 = hex_point((i + 1) % 6, EAVE_R - 0.02)
    qmid = (q0 + q1) / 2.0
    qout = qmid.normalized()
    qangle = math.atan2(q1.y - q0.y, q1.x - q0.x)
    add_box(f"SM_Pavilion_EaveFascia_{i + 1:02d}", (EAVE_R * 1.00, 0.075, 0.14),
            (qmid.x, qmid.y, EAVE_Z - 0.03), qangle, MAT_WOOD, COL_GEO, bevel=0.008)
    gold_pos = qmid + qout * 0.045
    add_box(f"SM_Pavilion_EaveFasciaGold_{i + 1:02d}", (EAVE_R * 1.01, 0.018, 0.025),
            (gold_pos.x, gold_pos.y, EAVE_Z - 0.095), qangle, MAT_GOLD, COL_GEO)

# Layered dougong bracket sets: six at column heads, six mid-span (bujian).
def add_dougong_set(name, center, tangent_angle, cross_angle, radial_angle):
    x, y, z = center
    add_box(f"{name}_Seat", (0.30, 0.28, 0.14), (x, y, z), tangent_angle,
            MAT_WOOD, COL_GEO, bevel=0.008)
    add_box(f"{name}_Qiao1", (0.62, 0.14, 0.10), (x, y, z + 0.11),
            tangent_angle, MAT_WOOD, COL_GEO, bevel=0.006)
    add_box(f"{name}_Qiao2", (0.44, 0.13, 0.09), (x, y, z + 0.19),
            cross_angle, MAT_PAINT, COL_GEO, bevel=0.005)
    add_box(f"{name}_LingGong", (0.96, 0.11, 0.08), (x, y, z + 0.27),
            tangent_angle, MAT_WOOD, COL_GEO, bevel=0.005)
    for side in (-1, 1):
        sx = x + math.cos(tangent_angle) * 0.42 * side
        sy = y + math.sin(tangent_angle) * 0.42 * side
        add_box(f"{name}_Sandou{'L' if side < 0 else 'R'}",
                (0.085, 0.085, 0.075), (sx, sy, z + 0.335), tangent_angle,
                MAT_GOLD, COL_GEO)
    # Slanted bracket arm (ang) pointing out and down.
    add_bar(f"{name}_Ang",
            (x - math.cos(radial_angle) * 0.04,
             y - math.sin(radial_angle) * 0.04, z + 0.21),
            (x + math.cos(radial_angle) * 0.36,
             y + math.sin(radial_angle) * 0.36, z + 0.03),
            0.055, MAT_WOOD, COL_GEO)


for i in range(6):
    p = hex_point(i, R_COL)
    tangent = math.radians(60.0 * i + 120.0)
    add_dougong_set(f"SM_Pavilion_DougongCol_{i + 1:02d}",
                    (p.x, p.y, COL_TOP + 0.02), tangent,
                    tangent - math.radians(60.0), math.radians(60.0 * i))

for i in range(6):
    mid_angle = math.radians(60.0 * i + 30.0)
    radius = R_COL * math.cos(math.radians(30.0)) + 0.06
    center = (math.cos(mid_angle) * radius, math.sin(mid_angle) * radius,
              COL_TOP + 0.02)
    tangent = math.radians(60.0 * i + 120.0)
    add_dougong_set(f"SM_Pavilion_DougongMid_{i + 1:02d}", center, tangent,
                    tangent + math.radians(90.0), mid_angle)

# ---------------------------------------------------------------------------
# Queti (corner brackets) and hanging lattice frieze (gualuo)
# ---------------------------------------------------------------------------

for i in range(6):
    p = hex_point(i, R_COL)
    for tag, direction_angle in (
            ("A", math.radians(60.0 * i + 120.0)),
            ("B", math.radians(60.0 * i + 60.0))):
        dx, dy = math.cos(direction_angle), math.sin(direction_angle)
        points = [
            (p.x + dx * 0.02, p.y + dy * 0.02, COL_TOP - 0.26),
            (p.x + dx * 0.17, p.y + dy * 0.17, COL_TOP - 0.16),
            (p.x + dx * 0.31, p.y + dy * 0.31, COL_TOP - 0.04),
        ]
        add_curve_tube(f"SM_Pavilion_Queti_{i + 1:02d}{tag}", points, 0.032,
                       MAT_WOOD, COL_GEO)

for i in range(6):
    if i == 4:
        continue
    p0 = hex_point(i, R_COL)
    p1 = hex_point((i + 1) % 6, R_COL)
    mid = (p0 + p1) / 2.0
    angle = math.atan2(p1.y - p0.y, p1.x - p0.x)
    z_top, z_bottom = COL_TOP - 0.15, COL_TOP - 0.43
    add_box(f"SM_Pavilion_GualuoTop_{i + 1:02d}", (HEX_SIDE * 0.90, 0.030, 0.035),
            (mid.x, mid.y, z_top), angle, MAT_WOOD, COL_GEO, bevel=0.004)
    add_box(f"SM_Pavilion_GualuoBottom_{i + 1:02d}", (HEX_SIDE * 0.90, 0.026, 0.028),
            (mid.x, mid.y, z_bottom), angle, MAT_WOOD, COL_GEO, bevel=0.004)
    for k in range(1, 10):
        point = p0.lerp(p1, k / 10.0)
        add_bar(f"SM_Pavilion_GualuoBar_{i + 1:02d}_{k:02d}",
                (point.x, point.y, z_bottom), (point.x, point.y, z_top),
                0.015, MAT_WOOD, COL_GEO)
    for k in range(4):
        t0 = 0.10 + 0.20 * k
        t1 = t0 + 0.20
        a = p0.lerp(p1, t0)
        b = p0.lerp(p1, t1)
        add_bar(f"SM_Pavilion_GualuoDiagA_{i + 1:02d}_{k + 1}",
                (a.x, a.y, z_bottom), (b.x, b.y, z_top), 0.012,
                MAT_WOOD, COL_GEO)
        add_bar(f"SM_Pavilion_GualuoDiagB_{i + 1:02d}_{k + 1}",
                (a.x, a.y, z_top), (b.x, b.y, z_bottom), 0.012,
                MAT_WOOD, COL_GEO)

# ---------------------------------------------------------------------------
# Railings on five sides (front side i == 4 stays open)
# ---------------------------------------------------------------------------

for i in range(6):
    if i == 4:
        continue
    p0 = hex_point(i, R_COL)
    p1 = hex_point((i + 1) % 6, R_COL)
    mid = (p0 + p1) / 2.0
    outward = mid.normalized()
    angle = math.atan2(p1.y - p0.y, p1.x - p0.x)
    # Bottom rail, seat board and outward-leaning backrest (meirenkao).
    add_box(f"SM_Pavilion_RailBottom_{i + 1:02d}", (HEX_SIDE * 0.94, 0.055, 0.055),
            (mid.x, mid.y, FLOOR_Z + 0.12), angle, MAT_WOOD, COL_GEO, bevel=0.006)
    seat_pos = mid + outward * 0.02
    add_box(f"SM_Pavilion_RailSeat_{i + 1:02d}", (HEX_SIDE * 0.94, 0.22, 0.05),
            (seat_pos.x, seat_pos.y, FLOOR_Z + 0.42), angle, MAT_WOOD,
            COL_GEO, bevel=0.006)
    top_pos = mid + outward * 0.06
    add_box(f"SM_Pavilion_RailTop_{i + 1:02d}", (HEX_SIDE * 0.94, 0.075, 0.07),
            (top_pos.x, top_pos.y, FLOOR_Z + 0.86), angle, MAT_WOOD,
            COL_GEO, bevel=0.006)
    add_box(f"SM_Pavilion_RailGold_{i + 1:02d}", (HEX_SIDE * 0.94, 0.020, 0.022),
            (top_pos.x, top_pos.y, FLOOR_Z + 0.925), angle, MAT_GOLD, COL_GEO)
    # Lower balusters between bottom rail and seat.
    for k in range(1, 6):
        t = k / 6.0
        point = p0.lerp(p1, t)
        add_bar(f"SM_Pavilion_Baluster_{i + 1:02d}_{k}",
                (point.x, point.y, FLOOR_Z + 0.15),
                (point.x, point.y, FLOOR_Z + 0.42), 0.032, MAT_WOOD, COL_GEO)
    # Seven curved back bars leaning outward.
    for k in range(1, 8):
        t = k / 8.0
        base = p0.lerp(p1, t)
        top = base + outward * 0.06
        add_bar(f"SM_Pavilion_RailBack_{i + 1:02d}_{k}",
                (base.x, base.y, FLOOR_Z + 0.45),
                (top.x, top.y, FLOOR_Z + 0.85), 0.024, MAT_WOOD, COL_GEO)
    # Two intermediate newel posts with gold caps.
    for k in (1, 2):
        point = p0.lerp(p1, k / 3.0)
        add_box(f"SM_Pavilion_RailPost_{i + 1:02d}_{k}",
                (0.075, 0.075, 0.90), (point.x, point.y, FLOOR_Z + 0.45),
                angle, MAT_WOOD, COL_GEO, bevel=0.006)
        add_sphere(f"SM_Pavilion_RailPostCap_{i + 1:02d}_{k}", 0.045,
                   (point.x, point.y, FLOOR_Z + 0.93), MAT_GOLD, COL_GEO,
                   segments=8, rings=4)

# ---------------------------------------------------------------------------
# Roof: continuous hexagonal curved surface
# ---------------------------------------------------------------------------


def roof_height(u, v):
    corner = abs(2.0 * u - 1.0)
    eave_z = EAVE_Z + CORNER_LIFT * (corner ** 2.5)
    return eave_z + (APEX_Z - eave_z) * (v ** 1.55)


def build_roof(segments_u=10, segments_v=12):
    verts = []
    faces = []
    ring_starts = []
    rings = []
    for iv in range(segments_v):
        v = iv / segments_v
        ring = []
        for i in range(6):
            p0 = hex_point(i, EAVE_R)
            p1 = hex_point((i + 1) % 6, EAVE_R)
            for iu in range(segments_u):
                u = iu / segments_u
                px = (p0.x + (p1.x - p0.x) * u) * (1.0 - v)
                py = (p0.y + (p1.y - p0.y) * u) * (1.0 - v)
                ring.append(len(verts))
                verts.append((px, py, roof_height(u, v)))
        rings.append(ring)
    apex = len(verts)
    verts.append((0.0, 0.0, APEX_Z))
    for iv in range(len(rings) - 1):
        lower, upper = rings[iv], rings[iv + 1]
        count = len(lower)
        for j in range(count):
            k = (j + 1) % count
            faces.append((lower[j], lower[k], upper[k], upper[j]))
    last = rings[-1]
    for j in range(len(last)):
        k = (j + 1) % len(last)
        faces.append((last[j], last[k], apex))
    return verts, faces


roof_verts, roof_faces = build_roof()
roof = add_mesh_object("SM_Pavilion_Roof", roof_verts, roof_faces, MAT_ROOF, COL_GEO)
add_solidify(roof, ROOF_THK, offset=0.0)
ensure_uv(roof)

# Eave gold trim around each side of the hexagonal eave.
for i in range(6):
    p0 = hex_point(i, EAVE_R + 0.015)
    p1 = hex_point((i + 1) % 6, EAVE_R + 0.015)
    points = []
    for k in range(5):
        t = k / 4.0
        u = t
        p = p0.lerp(p1, u)
        points.append((p.x, p.y, roof_height(u, 0.0) + 0.012))
    add_curve_tube(f"SM_Pavilion_EaveTrim_{i + 1:02d}", points, 0.026,
                   MAT_GOLD, COL_GEO)

# Hip ridges from apex to each lifted corner.
for i in range(6):
    corner = hex_point(i, EAVE_R)
    points = []
    for k in range(9):
        t = k / 8.0
        radius = EAVE_R * t
        p = hex_point(i, radius)
        # t=0 at apex, t=1 at eave corner.
        z = APEX_Z - (APEX_Z - (EAVE_Z + CORNER_LIFT)) * (t ** 1.55)
        points.append((p.x, p.y, z + 0.035))
    add_curve_tube(f"SM_Pavilion_HipRidge_{i + 1:02d}", points, 0.046,
                   MAT_STONE, COL_GEO)


def hip_point(i, t):
    radius = EAVE_R * t
    p = hex_point(i, radius)
    z = APEX_Z - (APEX_Z - (EAVE_Z + CORNER_LIFT)) * (t ** 1.55)
    return Vector((p.x, p.y, z))


# Three ceramic ridge beasts (zoushou) climbing each hip near the eave.
for i in range(6):
    angle = math.radians(60.0 * i)
    dx, dy = math.cos(angle), math.sin(angle)
    for k, t in enumerate((0.78, 0.85, 0.92)):
        base = hip_point(i, t)
        scale = 0.72 + 0.14 * k
        bx, by = base.x + dx * 0.035, base.y + dy * 0.035
        add_box(f"SM_Pavilion_RidgeBeast_{i + 1:02d}_{k + 1}",
                (0.065 * scale, 0.125 * scale, 0.075 * scale),
                (bx, by, base.z + 0.058 * scale), angle,
                MAT_STONE, COL_GEO, bevel=0.006)
        hx, hy = base.x + dx * (0.035 + 0.075 * scale), base.y + dy * (0.035 + 0.075 * scale)
        add_sphere(f"SM_Pavilion_RidgeBeastHead_{i + 1:02d}_{k + 1}",
                   0.034 * scale, (hx, hy, base.z + 0.085 * scale),
                   MAT_STONE, COL_GEO, segments=8, rings=4)
        tx, ty = base.x - dx * 0.045, base.y - dy * 0.045
        add_cone(f"SM_Pavilion_RidgeBeastTail_{i + 1:02d}_{k + 1}",
                 5, 0.022 * scale, 0.0, 0.08 * scale,
                 (tx, ty, base.z + 0.075 * scale),
                 (dx, dy, 0.35), MAT_STONE, COL_GEO)

# Seven convex tile courses per roof face, running eave to apex.
TILE_COURSES = 7
tile_courses = []
for i in range(6):
    p0 = hex_point(i, EAVE_R)
    p1 = hex_point((i + 1) % 6, EAVE_R)
    for k in range(TILE_COURSES):
        u = (k + 0.5) / TILE_COURSES
        points = []
        for step in range(7):
            v = (step / 6.0) * 0.93
            p = (p0 + (p1 - p0) * u) * (1.0 - v)
            points.append((p.x, p.y, roof_height(u, v) + ROOF_THK * 0.5 + 0.010))
        add_curve_tube(f"SM_Pavilion_TileCourse_{i + 1:02d}_{k + 1}",
                       points, 0.012, MAT_STONE, COL_GEO,
                       resolution_u=1, bevel_resolution=1)
        tile_courses.append((i, u))

# Round eave tile caps (wadang) at the end of every course.
for i, u in tile_courses:
    p0 = hex_point(i, EAVE_R)
    p1 = hex_point((i + 1) % 6, EAVE_R)
    p = p0.lerp(p1, u)
    out_dir = Vector((p.x, p.y, 0.16)).normalized()
    add_disc(f"SM_Pavilion_Wadang_{i + 1:02d}_{int(u * TILE_COURSES) + 1:02d}",
             0.034, 0.018, (p.x, p.y, roof_height(u, 0.0) + ROOF_THK * 0.5 + 0.010),
             out_dir, MAT_STONE, COL_GEO, vertices=10)

# Upturned corner spurs and gold tips.
for i in range(6):
    corner = hex_point(i, EAVE_R)
    outward = hex_point(i, 1.0)
    p0 = (corner.x, corner.y, EAVE_Z + CORNER_LIFT)
    p1 = (corner.x + outward.x * 0.28, corner.y + outward.y * 0.28,
          EAVE_Z + CORNER_LIFT + 0.13)
    p2 = (corner.x + outward.x * 0.52, corner.y + outward.y * 0.52,
          EAVE_Z + CORNER_LIFT + 0.32)
    add_curve_tube(f"SM_Pavilion_CornerSpur_{i + 1:02d}", [p0, p1, p2], 0.038,
                   MAT_STONE, COL_GEO)
    add_sphere(f"SM_Pavilion_CornerTip_{i + 1:02d}", 0.055, p2, MAT_GOLD,
               COL_GEO, segments=10, rings=5)

# Layered finial: stone base, lotus rings, bulb, stem, rings and spire.
add_hex_prism("SM_Pavilion_FinialBase", 0.28, APEX_Z, APEX_Z + 0.06,
              MAT_STONE, COL_GEO, bevel=0.008)
add_torus("SM_Pavilion_FinialLotusLow", 0.20, 0.035, (0, 0, APEX_Z + 0.09),
          (0, 0, 0), MAT_GOLD, COL_GEO, major_segments=16, minor_segments=4)
add_torus("SM_Pavilion_FinialLotusHigh", 0.15, 0.030, (0, 0, APEX_Z + 0.14),
          (0, 0, 0), MAT_GOLD, COL_GEO, major_segments=16, minor_segments=4)
add_sphere("SM_Pavilion_FinialBulb", 0.155, (0, 0, APEX_Z + 0.23), MAT_GOLD,
           COL_GEO, segments=16, rings=8)
add_cylinder("SM_Pavilion_FinialStem", 8, 0.040, 0.18, (0, 0, APEX_Z + 0.37),
             (0, 0, 0), MAT_GOLD, COL_GEO)
for index, z in enumerate((0.44, 0.48)):
    add_torus(f"SM_Pavilion_FinialRing_{index + 1}", 0.085, 0.018,
              (0, 0, APEX_Z + z), (0, 0, 0), MAT_GOLD, COL_GEO,
              major_segments=12, minor_segments=3)
add_sphere("SM_Pavilion_FinialTip", 0.068, (0, 0, APEX_Z + 0.54), MAT_GOLD,
           COL_GEO, segments=12, rings=6)
add_cone("SM_Pavilion_FinialSpire", 8, 0.048, 0.0, 0.16, (0, 0, APEX_Z + 0.64),
         (0, 0, 1), MAT_GOLD, COL_GEO)

# Six structural rafters visible from inside the open pavilion.
for i in range(6):
    p = hex_point(i, R_COL)
    add_bar(f"SM_Pavilion_Rafter_{i + 1:02d}",
            (0.0, 0.0, APEX_Z - 0.08), (p.x, p.y, COL_TOP + 0.02),
            0.075, MAT_WOOD, COL_GEO)

# Perimeter rafters under the eave, seven per side.
for i in range(6):
    p0_out = hex_point(i, EAVE_R - 0.03)
    p1_out = hex_point((i + 1) % 6, EAVE_R - 0.03)
    p0_in = hex_point(i, R_COL + 0.20)
    p1_in = hex_point((i + 1) % 6, R_COL + 0.20)
    for k in range(7):
        u = (k + 0.5) / 7.0
        outer = p0_out.lerp(p1_out, u)
        inner = p0_in.lerp(p1_in, u)
        add_bar(f"SM_Pavilion_EaveRafter_{i + 1:02d}_{k + 1}",
                (inner.x, inner.y, COL_TOP + 0.08),
                (outer.x, outer.y, roof_height(u, 0.0) - 0.06),
                0.050, MAT_WOOD, COL_GEO)

# ---------------------------------------------------------------------------
# Front plaque and text
# ---------------------------------------------------------------------------

PLAQUE_Z = 2.64
add_box("SM_Pavilion_Plaque", (1.34, 0.07, 0.46), (0.0, -1.705, PLAQUE_Z),
        0.0, MAT_WOOD, COL_GEO, bevel=0.014)
add_box("SM_Pavilion_PlaqueInlay", (1.22, 0.012, 0.36), (0.0, -1.744, PLAQUE_Z),
        0.0, MAT_PAINT, COL_GEO)
for z in (PLAQUE_Z - 0.245, PLAQUE_Z + 0.245):
    add_box(f"SM_Pavilion_PlaqueTrimH_{z:.3f}", (1.44, 0.035, 0.045),
            (0.0, -1.750, z), 0.0, MAT_GOLD, COL_GEO, bevel=0.005)
for x in (-0.70, 0.70):
    add_box(f"SM_Pavilion_PlaqueTrimV_{x:.2f}", (0.045, 0.035, 0.535),
            (x, -1.750, PLAQUE_Z), 0.0, MAT_GOLD, COL_GEO, bevel=0.005)
for x in (-0.70, 0.70):
    for z in (PLAQUE_Z - 0.245, PLAQUE_Z + 0.245):
        add_sphere(f"SM_Pavilion_PlaqueRosette_{x:.2f}_{z:.3f}", 0.040,
                   (x, -1.756, z), MAT_GOLD, COL_GEO, segments=8, rings=4)
for x in (-0.42, 0.42):
    add_cylinder(f"SM_Pavilion_PlaqueHanger_{x:.2f}", 8, 0.012, 0.10,
                 (x, -1.72, PLAQUE_Z + 0.28), (0, 0, 0), MAT_GOLD, COL_GEO)

FONT_PATH = "C:/Windows/Fonts/simhei.ttf"
try:
    plaque_font = bpy.data.fonts.load(FONT_PATH)
except Exception:
    plaque_font = None

bpy.ops.object.text_add(location=(0, 0, 0))
text_obj = bpy.context.object
text_obj.name = "SM_Pavilion_PlaqueText"
text_obj.data.body = "上元亭"
text_obj.data.size = 0.265
if plaque_font:
    text_obj.data.font = plaque_font
text_obj.data.extrude = 0.012
text_obj.data.align_x = "CENTER"
text_obj.data.align_y = "CENTER"
text_obj.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
activate(text_obj)
bpy.ops.object.convert(target="MESH")
text_obj = bpy.context.object
text_obj.name = "SM_Pavilion_PlaqueText"
apply_transform(text_obj)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=0.00001)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode="OBJECT")
text_obj.location = (0.0, -1.758, PLAQUE_Z)
apply_transform(text_obj)
dec = text_obj.modifiers.new("Decimate", "DECIMATE")
dec.ratio = 0.38
activate(text_obj)
bpy.ops.object.modifier_apply(modifier=dec.name)
text_obj.data.materials.append(MAT_GOLD)
move_to_collection(text_obj, COL_GEO)
ensure_uv(text_obj)

# ---------------------------------------------------------------------------
# Six small hanging lanterns at the eave corners
# ---------------------------------------------------------------------------

for i in range(6):
    corner = hex_point(i, 2.32)
    cx, cy = corner.x, corner.y
    # cord
    add_cylinder(f"SM_Pavilion_HangCord_{i + 1:02d}", 8, 0.006, 0.28,
                 (cx, cy, EAVE_Z + 0.02), (0, 0, 0), MAT_GOLD, COL_GEO)
    # body
    body = add_sphere(f"SM_Pavilion_Lantern_{i + 1:02d}", 0.145,
                      (cx, cy, EAVE_Z - 0.25), MAT_LANTERN, COL_GEO,
                      segments=12, rings=6, scale=(1.0, 1.0, 1.17))
    # top and bottom caps
    add_cylinder(f"SM_Pavilion_LanternTop_{i + 1:02d}", 8, 0.058, 0.035,
                 (cx, cy, EAVE_Z - 0.105), (0, 0, 0), MAT_GOLD, COL_GEO)
    add_cylinder(f"SM_Pavilion_LanternBottom_{i + 1:02d}", 8, 0.050, 0.030,
                 (cx, cy, EAVE_Z - 0.405), (0, 0, 0), MAT_GOLD, COL_GEO)
    # gold meridians on the paper body
    for rib in range(4):
        azimuth = math.radians(90.0 * rib)
        points = []
        for elevation in (-75.0, 0.0, 75.0):
            e = math.radians(elevation)
            points.append((cx + math.cos(azimuth) * 0.145 * math.cos(e),
                           cy + math.sin(azimuth) * 0.145 * math.cos(e),
                           EAVE_Z - 0.25 + 0.17 * math.sin(e)))
        add_curve_tube(f"SM_Pavilion_LanternRib_{i + 1:02d}_{rib + 1}",
                       points, 0.004, MAT_GOLD, COL_GEO,
                       resolution_u=1, bevel_resolution=0)
    # tassel
    add_sphere(f"SM_Pavilion_LanternBead_{i + 1:02d}", 0.025,
               (cx, cy, EAVE_Z - 0.445), MAT_GOLD, COL_GEO, segments=8, rings=4)
    add_cylinder(f"SM_Pavilion_LanternTassel_{i + 1:02d}", 6, 0.012, 0.18,
                 (cx, cy, EAVE_Z - 0.545), (0, 0, 0), MAT_LANTERN, COL_GEO)

# Larger lantern hanging in the centre of the pavilion, below the plaque line.
add_cylinder("SM_Pavilion_CenterLanternCord", 8, 0.008, 2.30, (0, 0, 3.42),
             (0, 0, 0), MAT_GOLD, COL_GEO)
add_sphere("SM_Pavilion_CenterLantern", 0.22, (0, 0, 2.00), MAT_LANTERN,
           COL_GEO, segments=14, rings=7, scale=(1.0, 1.0, 1.16))
add_cylinder("SM_Pavilion_CenterLanternTop", 10, 0.085, 0.045, (0, 0, 2.27),
             (0, 0, 0), MAT_GOLD, COL_GEO)
add_cylinder("SM_Pavilion_CenterLanternBottom", 10, 0.070, 0.040, (0, 0, 1.74),
             (0, 0, 0), MAT_GOLD, COL_GEO)
for rib in range(6):
    azimuth = math.radians(60.0 * rib)
    points = []
    for elevation in (-75.0, 0.0, 75.0):
        e = math.radians(elevation)
        points.append((math.cos(azimuth) * 0.22 * math.cos(e),
                       math.sin(azimuth) * 0.22 * math.cos(e),
                       2.00 + 0.255 * math.sin(e)))
    add_curve_tube(f"SM_Pavilion_CenterLanternRib_{rib + 1}", points, 0.005,
                   MAT_GOLD, COL_GEO, resolution_u=1, bevel_resolution=0)
add_sphere("SM_Pavilion_CenterLanternBead", 0.035, (0, 0, 1.69), MAT_GOLD,
           COL_GEO, segments=8, rings=4)
add_cylinder("SM_Pavilion_CenterLanternTassel", 6, 0.016, 0.26, (0, 0, 1.55),
             (0, 0, 0), MAT_LANTERN, COL_GEO)

# ---------------------------------------------------------------------------
# Join, clean, UV, origin, metadata
# ---------------------------------------------------------------------------

for obj in list(COL_GEO.objects):
    if obj.type == "MESH":
        ensure_uv(obj)

mesh_objects = sorted([o for o in COL_GEO.objects if o.type == "MESH"], key=lambda o: o.name)
bpy.ops.object.select_all(action="DESELECT")
for obj in mesh_objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = mesh_objects[0]
bpy.ops.object.join()
pavilion = bpy.context.object
pavilion.name = "SM_Env_Pavilion_Hex_01"
pavilion.data.name = "SM_Env_Pavilion_Hex_01_mesh"
move_to_collection(pavilion, COL_EXPORT)


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
    old_indices = [poly.material_index for poly in obj.data.polygons]
    obj.data.materials.clear()
    for material in unique:
        obj.data.materials.append(material)
    for poly, old_index in zip(obj.data.polygons, old_indices):
        poly.material_index = remap.get(old_index, old_index)


dedupe_material_slots(pavilion)

activate(pavilion)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.delete_loose(use_verts=True, use_edges=True, use_faces=False)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode="OBJECT")

# One packed UV set for future texturing / lightmaps.
activate(pavilion)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
try:
    bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.0015,
                             area_weight=0.0, correct_aspect=True,
                             scale_to_bounds=False)
except Exception as exc:
    print("UV_SMART_PROJECT_SKIPPED:", repr(exc))
bpy.ops.object.mode_set(mode="OBJECT")

uv_layer = pavilion.data.uv_layers.active
if uv_layer:
    for datum in uv_layer.data:
        u, v = datum.uv
        datum.uv = (min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0))

pavilion.location = (0.0, 0.0, 0.0)
pavilion.rotation_euler = (0.0, 0.0, 0.0)
pavilion.scale = (1.0, 1.0, 1.0)
shade_smooth_by_angle(pavilion, 32.0)

pavilion["asset_name"] = "SM_Env_Pavilion_Hex_01"
pavilion["asset_type"] = "Hexagonal garden pavilion / festival landmark"
pavilion["dimensions_m"] = (f"{pavilion.dimensions.x:.2f} x {pavilion.dimensions.y:.2f} x "
                            f"{pavilion.dimensions.z:.2f} m (bounding box); column clear height 2.55 m")
pavilion["pivot"] = "Center of podium at ground (0,0,0)"
pavilion["forward"] = "-Y (front steps and plaque)"
pavilion["source_notes"] = "Six-column Chinese garden pavilion; curved eave roof; target Unity URP mobile"

# Save the clean, engine-ready asset before the look-dev rig is added.
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(EXPORT_DIR, "SM_Env_Pavilion_Hex_01.blend"))

# ---------------------------------------------------------------------------
# Look-dev scene: night garden, backdrop, lights, cameras
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
    mat = bpy.data.materials.new("MAT_Pavilion_Backdrop")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 0.55
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.003, 0.008, 0.011, 1)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.012, 0.050, 0.058, 1)
    texco = nodes.new("ShaderNodeTexCoord")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    links.new(texco.outputs["Generated"], separate.inputs["Vector"])
    links.new(separate.outputs["Z"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = (0.008, 0.02, 0.025, 1)
    return mat


MAT_BACKDROP = make_gradient_backdrop_material()

bpy.ops.mesh.primitive_cylinder_add(
    vertices=64, radius=14.0, depth=20.0, end_fill_type="NOTHING",
    location=(0, 0, 4.0))
backdrop = bpy.context.object
backdrop.name = "SM_Pavilion_Backdrop"
backdrop.data.materials.append(MAT_BACKDROP)
move_to_collection(backdrop, COL_RENDER)
for poly in backdrop.data.polygons:
    poly.use_smooth = True

bpy.ops.mesh.primitive_plane_add(size=40.0, location=(0, 0, 0))
ground = bpy.context.object
ground.name = "SM_Pavilion_Ground"
mat_ground = make_material("MAT_Render_Ground", base=(0.012, 0.010, 0.009), roughness=0.42)
ground.data.materials.append(mat_ground)
move_to_collection(ground, COL_RENDER)

# A few warm bokeh spheres behind the pavilion.
MAT_BOKEH_A = make_emission_material("MAT_Pavilion_BokehWarm", (1.0, 0.26, 0.05), 4.5)
MAT_BOKEH_B = make_emission_material("MAT_Pavilion_BokehRed", (0.9, 0.04, 0.02), 3.5)
bokeh_positions = [
    (-6.5, 7.5, 3.6, 0.16), (-4.8, 8.2, 2.8, 0.12), (-2.5, 7.8, 4.4, 0.18),
    (3.2, 8.4, 3.4, 0.14), (5.4, 7.4, 4.8, 0.20), (1.2, 9.0, 2.2, 0.10),
]
for index, (x, y, z, radius) in enumerate(bokeh_positions):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=5, radius=radius,
                                         location=(x, y, z))
    sphere = bpy.context.object
    sphere.name = f"SM_Pavilion_Bokeh_{index + 1:02d}"
    sphere.data.materials.append(MAT_BOKEH_A if index % 2 == 0 else MAT_BOKEH_B)
    move_to_collection(sphere, COL_RENDER)


def add_area_light(name, location, energy, color, size, target=(0, 0, 2.5)):
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


add_area_light("LGT_Pavilion_Key", (-6.5, -7.5, 7.0), 900.0, (1.0, 0.84, 0.68), 4.0)
add_area_light("LGT_Pavilion_Fill", (7.5, -5.0, 4.5), 320.0, (0.35, 0.55, 0.95), 5.0)
add_area_light("LGT_Pavilion_Rim", (0.0, 8.0, 6.5), 650.0, (1.0, 0.42, 0.16), 3.0)
add_area_light("LGT_Pavilion_Bounce", (0.0, -4.5, 0.8), 160.0, (1.0, 0.45, 0.20), 3.0,
               target=(0, 0, 1.2))

# Interior warm lights.
for index, z in enumerate((1.6, 2.55)):
    data = bpy.data.lights.new(f"LGT_Pavilion_Inner_{index + 1}", type="POINT")
    data.energy = 90.0 if index else 60.0
    data.color = (1.0, 0.32, 0.07)
    data.shadow_soft_size = 0.25
    obj = bpy.data.objects.new(f"LGT_Pavilion_Inner_{index + 1}", data)
    COL_LIGHTS.objects.link(obj)
    obj.location = (0, 0, z)

# Small warm lights at the six hanging lanterns.
for i in range(6):
    corner = hex_point(i, 2.32)
    data = bpy.data.lights.new(f"LGT_Pavilion_Lantern_{i + 1:02d}", type="POINT")
    data.energy = 10.0
    data.color = (1.0, 0.22, 0.04)
    data.shadow_soft_size = 0.10
    obj = bpy.data.objects.new(f"LGT_Pavilion_Lantern_{i + 1:02d}", data)
    COL_LIGHTS.objects.link(obj)
    obj.location = (corner.x, corner.y, EAVE_Z - 0.25)


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


CAM_HERO = add_camera("CAM_Pavilion_Hero", (7.4, -10.2, 4.0), (0, 0, 2.4), 46.0)
CAM_FRONT = add_camera("CAM_Pavilion_Front", (0, -13.5, 3.3), (0, 0, 2.55), 50.0)
CAM_RIGHT = add_camera("CAM_Pavilion_Right", (12.0, 0, 3.3), (0, 0, 2.55), 40.0)
CAM_BACK = add_camera("CAM_Pavilion_Back", (0, 12.4, 3.4), (0, 0, 2.55), 50.0)
CAM_THREE = add_camera("CAM_Pavilion_ThreeQuarter", (-7.0, -9.5, 4.0), (0, 0, 2.4), 48.0)
CAM_DETAIL_ROOF = add_camera("CAM_Pavilion_DetailRoof", (4.9, -6.8, 7.4), (0, 0, 4.2), 72.0)
CAM_DETAIL_EAVE = add_camera("CAM_Pavilion_DetailEave", (3.8, -5.6, 2.75), (0.7, -1.45, 2.45), 65.0)
CAM_DETAIL_DOUGONG = add_camera("CAM_Pavilion_DetailDougong", (4.4, -3.6, 2.2),
                                (1.3, -1.2, 3.05), 65.0)
CAM_DETAIL_RAILING = add_camera("CAM_Pavilion_DetailRailing", (2.9, -4.9, 2.0),
                                (0.35, -1.25, 1.15), 72.0)

# Depth of field on hero and detail shots.
for cam, fstop in ((CAM_HERO, 4.0), (CAM_THREE, 4.5), (CAM_DETAIL_EAVE, 3.5),
                   (CAM_DETAIL_DOUGONG, 4.5), (CAM_DETAIL_RAILING, 3.2)):
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = pavilion
    cam.data.dof.aperture_fstop = fstop

# World and render settings.
world = bpy.data.worlds.new("W_Pavilion_World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.003, 0.008, 0.010, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.24

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

LOOKDEV_PATH = os.path.join(EXPORT_DIR, "SM_Env_Pavilion_Hex_01_lookdev.blend")
bpy.ops.wm.save_as_mainfile(filepath=LOOKDEV_PATH)

# Export selected mesh only.
bpy.ops.object.select_all(action="DESELECT")
pavilion.select_set(True)
bpy.context.view_layer.objects.active = pavilion
glb_path = os.path.join(EXPORT_DIR, "SM_Env_Pavilion_Hex_01.glb")
bpy.ops.export_scene.gltf(
    filepath=glb_path, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT",
    export_texcoords=True, export_normals=True, export_cameras=False,
    export_lights=False)

fbx_path = os.path.join(EXPORT_DIR, "SM_Env_Pavilion_Hex_01.fbx")
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
    if os.environ.get("PAVILION_SKIP_RENDER") == "1":
        return scene.render.filepath
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as exc:
        render_errors.append({"view": filename, "error": repr(exc)})
        print("RENDER_FAILED:", filename, repr(exc))
    return scene.render.filepath


render_view(CAM_HERO, "hero.png", 1080, 1350, 64)
render_view(CAM_THREE, "three_quarter.png", 1080, 1350, 48)
render_view(CAM_DETAIL_ROOF, "detail_roof.png", 1000, 1000, 48)
render_view(CAM_DETAIL_EAVE, "detail_eave.png", 1000, 1000, 48)
render_view(CAM_DETAIL_DOUGONG, "detail_dougong.png", 1000, 1000, 48)
render_view(CAM_DETAIL_RAILING, "detail_railing.png", 1000, 1000, 48)

for obj in [o for o in COL_RENDER.objects if o.name.startswith("SM_Pavilion_Bokeh")]:
    obj.hide_render = True
render_view(CAM_FRONT, "front.png", 800, 1000, 32)
render_view(CAM_RIGHT, "right.png", 800, 1000, 32)
render_view(CAM_BACK, "back.png", 800, 1000, 32)
for obj in [o for o in COL_RENDER.objects if o.name.startswith("SM_Pavilion_Bokeh")]:
    obj.hide_render = False

# Restore hero camera and save lookdev.
scene.camera = CAM_HERO
scene.render.resolution_x = 1080
scene.render.resolution_y = 1350
scene.eevee.taa_render_samples = 64
scene.render.filepath = os.path.join(RAW_RENDER_DIR, "hero.png")
bpy.ops.wm.save_as_mainfile(filepath=LOOKDEV_PATH)

# Report stats.
tris = sum(len(p.vertices) - 2 for p in pavilion.data.polygons)
report = {
    "asset": "SM_Env_Pavilion_Hex_01",
    "triangles": tris,
    "vertices": len(pavilion.data.vertices),
    "materials": [slot.material.name for slot in pavilion.material_slots if slot.material],
    "dimensions_m": list(pavilion.dimensions),
    "pivot": "center of podium at ground",
    "exports": {
        "blend": os.path.join(EXPORT_DIR, "SM_Env_Pavilion_Hex_01.blend"),
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
