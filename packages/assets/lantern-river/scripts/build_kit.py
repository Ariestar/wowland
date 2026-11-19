"""Build the Lantern River modular kit — Portal-derived night-market kit.

Run:
    blender -b --python assets/lantern-river/scripts/build_kit.py

Outputs:
    assets/lantern-river/exports/SM_Env_LanternRiver_Kit.blend
    assets/lantern-river/exports/kit/*.glb / *.fbx
    assets/lantern-river/reports/kit_report.json

Design source: Portals / lantern-river (Three.js procedural world).
Converted to a Blender-authored, game-ready Unity URP kit:
  - 3 shophouse variants (8–10 m wide, 2–3 floors)
  - 1 stone arch bridge (44 m span, red railing)
  - 1 five-tier lantern tower (19 m, landmark)
  - hung lantern, sky lantern, 28 m lantern string
  - market stall
All dimensions in metres, pivot at base centre, front facade faces local -Y.
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
KIT_DIR = os.path.join(EXPORT_DIR, "kit")
REPORT_DIR = os.path.join(ASSET_DIR, "reports")
for path in (EXPORT_DIR, KIT_DIR, REPORT_DIR):
    os.makedirs(path, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    if parent is not None:
        parent.children.link(col)
    else:
        scene.collection.children.link(col)
    return col


COL_ROOT = new_collection("COL_LanternRiver_Kit")
COL_KIT = new_collection("COL_Kit", COL_ROOT)
COL_EXPORT = new_collection("COL_Export", COL_ROOT)


# ---------------------------------------------------------------------------
# Colour / material helpers
# ---------------------------------------------------------------------------

def srgb(hex_value):
    """Convert #RRGGBB sRGB to Blender linear RGB."""
    value = hex_value.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(value[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def make_material(name, hex_base, metallic=0.0, roughness=0.5, emission=None,
                  emission_strength=0.0, coat=0.0, sheen=0.0, bump=0.0,
                  bump_scale=8.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    base = srgb(hex_base)
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Coat Weight"].default_value = coat
    bsdf.inputs["Sheen Weight"].default_value = sheen
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*srgb(emission), 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if bump > 0:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = bump_scale
        tex.inputs["Detail"].default_value = 3.0
        tex.inputs["Roughness"].default_value = 0.55
        bump_node = nt.nodes.new("ShaderNodeBump")
        bump_node.inputs["Strength"].default_value = bump
        bump_node.inputs["Distance"].default_value = 0.06
        nt.links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
        nt.links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    mat.diffuse_color = (*base, 1.0)
    return mat


MAT_WOOD = make_material("MAT_LR_Wood_Dark", "#33221C", roughness=0.38, coat=0.18,
                         bump=0.10, bump_scale=18.0)
MAT_WOOD_WARM = make_material("MAT_LR_Wood_Warm", "#4A2F20", roughness=0.42, coat=0.15,
                              bump=0.10, bump_scale=16.0)
MAT_PLASTER = make_material("MAT_LR_Plaster_Warm", "#E8DFCC", roughness=0.72,
                            bump=0.14, bump_scale=28.0)
MAT_PLASTER_2 = make_material("MAT_LR_Plaster_Sand", "#D8CDB8", roughness=0.75,
                              bump=0.14, bump_scale=28.0)
MAT_ROOF = make_material("MAT_LR_Roof_Tile", "#27333A", metallic=0.10, roughness=0.34,
                         coat=0.22, bump=0.10, bump_scale=35.0)
MAT_ROOF_2 = make_material("MAT_LR_Roof_Blue", "#2B3D3A", metallic=0.08, roughness=0.36,
                           coat=0.18, bump=0.10, bump_scale=35.0)
MAT_LACQUER = make_material("MAT_LR_Lacquer_Red", "#A32E1B", roughness=0.40, coat=0.35,
                            bump=0.05, bump_scale=24.0)
MAT_STONE = make_material("MAT_LR_Stone", "#66626E", roughness=0.78,
                          bump=0.18, bump_scale=20.0)
MAT_STONE_LIGHT = make_material("MAT_LR_Stone_Light", "#8D8A82", roughness=0.74,
                                bump=0.16, bump_scale=22.0)
MAT_GOLD = make_material("MAT_LR_Gold", "#D8B45A", metallic=1.0, roughness=0.28, coat=0.10)
MAT_PAPER = make_material("MAT_LR_Paper_Glow", "#FFD9A0", roughness=0.55,
                          emission="#FFB35A", emission_strength=3.2, sheen=0.15)
MAT_PAPER_RED = make_material("MAT_LR_Paper_Red", "#FF6A3A", roughness=0.55,
                              emission="#FF4D3D", emission_strength=2.8, sheen=0.10)
MAT_WATER = make_material("MAT_LR_Water", "#0B1640", metallic=0.25, roughness=0.08,
                          coat=0.6)
MAT_CLOTH_RED = make_material("MAT_LR_Cloth_Red", "#A8382E", roughness=0.82, sheen=0.2)
MAT_CLOTH_CREAM = make_material("MAT_LR_Cloth_Cream", "#E3D5B8", roughness=0.85, sheen=0.2)


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


def add_box(name, size, location, material, collection, rotation=(0, 0, 0),
            bevel=0.0, bevel_segments=1):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
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


def add_cylinder(name, vertices, radius, depth, location, material, collection,
                 rotation=(0, 0, 0), bevel=0.0, bevel_segments=1):
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


def add_cone(name, vertices, radius1, radius2, depth, location, material, collection,
             rotation=(0, 0, 0)):
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


def add_sphere(name, radius, location, material, collection, segments=16, rings=8,
               scale=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings,
                                         radius=radius, location=location)
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


def add_mesh_object(name, verts, faces, material, collection):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    recalc_normals(obj)
    return obj


def add_staircase(name, width, steps, tread, riser, front_y, base_z, material, collection):
    """Watertight stepped prism, ascending from front_y toward +Y."""
    half = width / 2.0
    profile = [(front_y, base_z)]
    for i in range(steps):
        y0 = front_y + i * tread
        z0 = base_z + i * riser
        profile.append((y0, z0 + riser))
        profile.append((y0 + tread, z0 + riser))
    profile.append((front_y + steps * tread, base_z))
    verts = []
    for x in (-half, half):
        for y, z in profile:
            verts.append((x, y, z))
    n = len(profile)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    obj = add_mesh_object(name, verts, faces, material, collection)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def recalc_normals(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def add_solidify(obj, thickness, offset=0.0):
    mod = obj.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = offset
    mod.use_even_offset = True
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    recalc_normals(obj)


def add_curve_tube(name, points, radius, material, collection, cyclic=False,
                   resolution_u=2, bevel_resolution=1):
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


def add_lathe(name, profile, segments, material, collection, smooth=True):
    """Lathe a [(radius, z), ...] profile around Z. Closed with caps."""
    verts = []
    rings = []
    for radius, z in profile:
        if radius <= 1e-7:
            rings.append([len(verts)])
            verts.append((0.0, 0.0, z))
        else:
            ring = []
            for i in range(segments):
                angle = 2.0 * math.pi * i / segments
                ring.append(len(verts))
                verts.append((radius * math.cos(angle), radius * math.sin(angle), z))
            rings.append(ring)
    faces = []
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for i in range(len(b)):
                faces.append((a[0], b[i], b[(i + 1) % len(b)]))
        elif len(b) == 1:
            for i in range(len(a)):
                faces.append((a[i], a[(i + 1) % len(a)], b[0]))
        else:
            for i in range(len(a)):
                j = (i + 1) % len(a)
                faces.append((a[i], a[j], b[j], b[i]))
    # Close profiles that end on a nonzero radius so each lathe piece is watertight.
    if len(rings[0]) > 1:
        centre = len(verts)
        verts.append((0.0, 0.0, profile[0][1]))
        for i in range(len(rings[0])):
            faces.append((rings[0][i], rings[0][(i + 1) % len(rings[0])], centre))
    if len(rings[-1]) > 1:
        centre = len(verts)
        verts.append((0.0, 0.0, profile[-1][1]))
        for i in range(len(rings[-1])):
            faces.append((centre, rings[-1][i], rings[-1][(i + 1) % len(rings[-1])]))
    obj = add_mesh_object(name, verts, faces, material, collection)
    if smooth:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    return obj


def box_project_uv(obj):
    if obj.data.uv_layers:
        return
    mesh = obj.data
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
                u, v, su, sv, ou, ov = co.y, co.z, spans[1], spans[2], mins[1], mins[2]
            elif axis == 1:
                u, v, su, sv, ou, ov = co.x, co.z, spans[0], spans[2], mins[0], mins[2]
            else:
                u, v, su, sv, ou, ov = co.x, co.y, spans[0], spans[1], mins[0], mins[1]
            uv.data[li].uv = ((u - ou) / su, (v - ov) / sv)


def finalize_kit(obj, name, tri_budget):
    """Common cleanup for a kit piece."""
    obj.name = name
    obj.data.name = name + "_mesh"
    activate(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.00002)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    # Smart UV + a fresh 0–1 pack.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    for poly in obj.data.polygons:
        poly.use_smooth = False
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(32))
    move_to_collection(obj, COL_KIT)
    return obj


def join_parts(parts, name):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = name
    return obj


# ---------------------------------------------------------------------------
# Lantern props
# ---------------------------------------------------------------------------

def build_hung_lantern(name, scale=1.0):
    """Classic round festival lantern, pivot at hanging point (top)."""
    s = scale
    parts = []
    # Body: lathe around Z, top at z=0, bottom at z=-0.62.
    profile = [
        (0.02, 0.00), (0.16, -0.04), (0.24, -0.16), (0.27, -0.31),
        (0.24, -0.46), (0.15, -0.56), (0.02, -0.60),
    ]
    body = add_lathe(f"{name}_Body", [(r * s, z * s) for r, z in profile], 10,
                     MAT_PAPER, COL_KIT)
    parts.append(body)
    # Top and bottom caps.
    parts.append(add_cylinder(f"{name}_CapTop", 10, 0.12 * s, 0.045 * s,
                              (0, 0, 0.015 * s), MAT_GOLD, COL_KIT))
    parts.append(add_cylinder(f"{name}_CapBot", 10, 0.10 * s, 0.04 * s,
                              (0, 0, -0.61 * s), MAT_GOLD, COL_KIT))
    # Hanging hook + tassel.
    parts.append(add_cylinder(f"{name}_Hook", 6, 0.018 * s, 0.20 * s,
                              (0, 0, 0.13 * s), MAT_GOLD, COL_KIT))
    parts.append(add_cylinder(f"{name}_Tassel", 6, 0.018 * s, 0.28 * s,
                              (0, 0, -0.75 * s), MAT_LACQUER, COL_KIT))
    parts.append(add_cylinder(f"{name}_TasselTip", 6, 0.045 * s, 0.06 * s,
                              (0, 0, -0.91 * s), MAT_GOLD, COL_KIT))
    obj = join_parts(parts, name)
    return finalize_kit(obj, name, 900)


def build_sky_lantern(name):
    """Sky lantern: 1.0 m tall, pivot at bottom centre."""
    profile = [
        (0.16, 0.00), (0.30, 0.06), (0.42, 0.22), (0.48, 0.44),
        (0.50, 0.66), (0.46, 0.84), (0.34, 0.96), (0.16, 1.00), (0.02, 1.00),
    ]
    body = add_lathe(name + "_Body", profile, 10, MAT_PAPER, COL_KIT)
    rim = add_cylinder(name + "_Rim", 10, 0.17, 0.035, (0, 0, 0.015),
                       MAT_WOOD, COL_KIT)
    obj = join_parts([body, rim], name)
    return finalize_kit(obj, name, 500)


def build_lantern_string(name, span=28.0, height=9.0, sag=1.8, spacing=1.4):
    """A catenary lantern string with low-poly bulbs and end posts."""
    parts = []
    count = max(4, int(span / spacing))
    points = []
    for i in range(count + 1):
        t = i / count
        x = -span / 2 + span * t
        z = height - sag * 4 * t * (1 - t)
        points.append((x, 0.0, z))
    parts.append(add_curve_tube(name + "_Wire", points, 0.012, MAT_WOOD, COL_KIT,
                                resolution_u=2, bevel_resolution=1))
    for i in range(1, count):
        t = i / count
        x = -span / 2 + span * t
        z = height - sag * 4 * t * (1 - t) - 0.12
        parts.append(add_sphere(f"{name}_Bulb_{i:02d}", 0.10, (x, 0, z),
                                MAT_PAPER, COL_KIT, segments=8, rings=4))
    # End posts with a small lantern on top.
    for side in (-1, 1):
        x = side * span / 2
        parts.append(add_cylinder(f"{name}_Post_{side}", 8, 0.09, height,
                                  (x, 0, height / 2), MAT_WOOD, COL_KIT))
        parts.append(add_cylinder(f"{name}_PostBase_{side}", 8, 0.20, 0.18,
                                  (x, 0, 0.09), MAT_STONE, COL_KIT))
        parts.append(add_sphere(f"{name}_PostLamp_{side}", 0.16, (x, 0, height + 0.18),
                                MAT_PAPER, COL_KIT, segments=8, rings=4))
    obj = join_parts(parts, name)
    return finalize_kit(obj, name, 2500)


# ---------------------------------------------------------------------------
# Shophouse
# ---------------------------------------------------------------------------

def add_window(parts, prefix, x, z_center, width, height, facade_y, outward=-1,
               cols=4, rows=3, shutters=False, transom=False):
    """Recessed timber window: casing, projecting sill, paper, lattice, shutters."""
    y0 = facade_y + outward * 0.02
    jamb = 0.075
    # Deep casing: jambs stand proud of the plaster, paper sits inside.
    parts.append(add_box(f"{prefix}_JambL", (jamb, 0.19, height + 0.24),
                         (x - width / 2 - jamb / 2, y0 + outward * 0.045, z_center),
                         MAT_WOOD, COL_KIT, bevel=0.008))
    parts.append(add_box(f"{prefix}_JambR", (jamb, 0.19, height + 0.24),
                         (x + width / 2 + jamb / 2, y0 + outward * 0.045, z_center),
                         MAT_WOOD, COL_KIT, bevel=0.008))
    parts.append(add_box(f"{prefix}_Lintel", (width + 2 * jamb + 0.18, 0.21, 0.12),
                         (x, y0 + outward * 0.05, z_center + height / 2 + 0.08),
                         MAT_WOOD, COL_KIT, bevel=0.01))
    parts.append(add_box(f"{prefix}_Sill", (width + 2 * jamb + 0.26, 0.27, 0.09),
                         (x, y0 + outward * 0.09, z_center - height / 2 - 0.05),
                         MAT_WOOD_WARM, COL_KIT, bevel=0.012))
    # Paper is inset so the lattice casts a soft shadow line.
    parts.append(add_box(f"{prefix}_Paper", (width, 0.03, height),
                         (x, y0 - outward * 0.02, z_center), MAT_PAPER, COL_KIT))
    # Lattice grid.
    for i in range(cols - 1):
        bx = x - width / 2 + width * (i + 1) / cols
        parts.append(add_box(f"{prefix}_BarV{i}", (0.032, 0.05, height),
                             (bx, y0 + outward * 0.02, z_center), MAT_WOOD, COL_KIT))
    for j in range(rows - 1):
        bz = z_center - height / 2 + height * (j + 1) / rows
        parts.append(add_box(f"{prefix}_BarH{j}", (width, 0.05, 0.032),
                             (x, y0 + outward * 0.02, bz), MAT_WOOD, COL_KIT))
    if transom:
        tz = z_center + height / 2 + 0.32
        parts.append(add_box(f"{prefix}_TransomPaper", (width, 0.03, 0.30),
                             (x, y0 - outward * 0.02, tz), MAT_PAPER, COL_KIT))
        for i in range(3):
            bx = x - width / 2 + width * (i + 1) / 4
            parts.append(add_box(f"{prefix}_TransomBar{i}", (0.028, 0.05, 0.30),
                                 (bx, y0 + outward * 0.02, tz), MAT_WOOD, COL_KIT))
        parts.append(add_box(f"{prefix}_TransomRail", (width + 0.18, 0.12, 0.07),
                             (x, y0 + outward * 0.04, tz - 0.19), MAT_WOOD, COL_KIT))
    if shutters:
        for side in (-1, 1):
            sx = x + side * (width / 2 + jamb + 0.16)
            parts.append(add_box(f"{prefix}_Shutter{side}", (0.20, 0.05, height * 0.94),
                                 (sx, y0 + outward * 0.06, z_center), MAT_WOOD_WARM, COL_KIT))
            for j in range(3):
                bz = z_center - height * 0.36 + height * 0.36 * j
                parts.append(add_box(f"{prefix}_ShutterSlat{side}{j}", (0.16, 0.06, 0.04),
                                     (sx, y0 + outward * 0.08, bz), MAT_WOOD, COL_KIT))


def add_side_window(parts, prefix, side_x, y, z_center, width, height, outward):
    """Window in a gable wall, facing ±X."""
    x0 = side_x + outward * 0.02
    parts.append(add_box(f"{prefix}_SidePaper", (0.03, width, height),
                         (x0 - outward * 0.02, y, z_center), MAT_PAPER, COL_KIT))
    parts.append(add_box(f"{prefix}_SideSill", (0.16, width + 0.22, 0.08),
                         (x0 + outward * 0.05, y, z_center - height / 2 - 0.04),
                         MAT_WOOD_WARM, COL_KIT))
    for i in range(3):
        by = y - width / 2 + width * (i + 1) / 4
        parts.append(add_box(f"{prefix}_SideBarV{i}", (0.05, 0.03, height),
                             (x0 + outward * 0.02, by, z_center), MAT_WOOD, COL_KIT))
    for j in range(2):
        bz = z_center - height / 2 + height * (j + 1) / 3
        parts.append(add_box(f"{prefix}_SideBarH{j}", (0.05, width, 0.03),
                             (x0 + outward * 0.02, y, bz), MAT_WOOD, COL_KIT))


def add_dougong(parts, prefix, width, facade_y, eave_z, count, outward=-1):
    """Continuous architrave plus stepped bracket sets under a shophouse eave."""
    parts.append(add_box(f"{prefix}_Architrave", (width + 0.12, 0.20, 0.13),
                         (0, facade_y + outward * 0.08, eave_z - 0.10),
                         MAT_WOOD, COL_KIT))
    for i in range(count):
        cx = -width / 2 + width * (i + 0.5) / count
        parts.append(add_box(f"{prefix}_BracketA{i}", (0.36, 0.18, 0.10),
                             (cx, facade_y + outward * 0.12, eave_z - 0.24),
                             MAT_WOOD, COL_KIT))
        parts.append(add_box(f"{prefix}_BracketB{i}", (0.24, 0.34, 0.10),
                             (cx, facade_y + outward * 0.24, eave_z - 0.15),
                             MAT_WOOD_WARM, COL_KIT))
        parts.append(add_box(f"{prefix}_BracketC{i}", (0.14, 0.48, 0.09),
                             (cx, facade_y + outward * 0.38, eave_z - 0.06),
                             MAT_WOOD, COL_KIT))


def add_shop_awning(parts, prefix, width, facade_y, z, cloth_mat):
    """Sloped canvas awning with a scalloped valance over the shopfront."""
    w = width * 0.92
    parts.append(add_box(f"{prefix}_Awning", (w, 1.15, 0.055),
                         (0, facade_y - 0.56, z - 0.12), cloth_mat, COL_KIT,
                         rotation=(-0.24, 0, 0)))
    parts.append(add_box(f"{prefix}_AwningRod", (0.05, 1.30, 0.05),
                         (-w / 2 + 0.08, facade_y - 0.56, z - 0.05), MAT_WOOD, COL_KIT,
                         rotation=(-0.24, 0, 0)))
    parts.append(add_box(f"{prefix}_AwningRod2", (0.05, 1.30, 0.05),
                         (w / 2 - 0.08, facade_y - 0.56, z - 0.05), MAT_WOOD, COL_KIT,
                         rotation=(-0.24, 0, 0)))
    # Scalloped cream valance: narrow strips read as cloth folds at distance.
    strips = max(6, int(w / 0.34))
    for i in range(strips):
        sx = -w / 2 + w * (i + 0.5) / strips
        parts.append(add_box(f"{prefix}_Valance{i}", (w / strips * 0.72, 0.035, 0.26),
                             (sx, facade_y - 1.10, z - 0.40), MAT_CLOTH_CREAM, COL_KIT))


def add_shop_sign(parts, prefix, x, facade_y, z, side):
    """Perpendicular hanging shop sign, visible down the street."""
    parts.append(add_box(f"{prefix}_SignArm", (0.05, 0.72, 0.05),
                         (x, facade_y - 0.34, z + 0.42), MAT_WOOD, COL_KIT))
    parts.append(add_box(f"{prefix}_SignBoard", (0.08, 0.62, 0.72),
                         (x, facade_y - 0.64, z), MAT_LACQUER, COL_KIT,
                         bevel=0.012))
    for dz in (-0.26, 0.0, 0.26):
        parts.append(add_box(f"{prefix}_SignSlat{dz:.2f}", (0.10, 0.52, 0.05),
                             (x, facade_y - 0.64, z + dz), MAT_GOLD, COL_KIT))
    parts.append(add_cylinder(f"{prefix}_SignTassel", 4, 0.028, 0.28,
                              (x, facade_y - 0.64, z - 0.50), MAT_LACQUER, COL_KIT))


def add_eave_caps_x(parts, prefix, x0, x1, y, z, count, material):
    for i in range(count):
        x = x0 + (x1 - x0) * (i + 0.5) / count
        parts.append(add_cylinder(f"{prefix}_CapX{i}", 7, 0.052, 0.075,
                                  (x, y, z), material, COL_KIT,
                                  rotation=(math.pi / 2, 0, 0)))


def add_eave_caps_y(parts, prefix, y0, y1, x, z, count, material):
    for i in range(count):
        y = y0 + (y1 - y0) * (i + 0.5) / count
        parts.append(add_cylinder(f"{prefix}_CapY{i}", 7, 0.052, 0.075,
                                  (x, y, z), material, COL_KIT,
                                  rotation=(0, math.pi / 2, 0)))


def add_railing_ring(parts, prefix, radius, z, segments=8, post_count=16,
                     mat=MAT_LACQUER, height=0.82):
    """Octagonal balcony railing: corner posts plus top/mid rails."""
    for i in range(post_count):
        a = math.tau * i / post_count
        px, py = radius * math.cos(a), radius * math.sin(a)
        parts.append(add_box(f"{prefix}_Post{i}", (0.055, 0.055, height),
                             (px, py, z + height / 2), mat, COL_KIT,
                             rotation=(0, 0, a)))
        if i % 2 == 0:
            parts.append(add_box(f"{prefix}_Baluster{i}", (0.03, 0.03, height * 0.62),
                                 (px * 0.995, py * 0.995, z + height * 0.36),
                                 MAT_WOOD, COL_KIT))
    for ring_i, rz in enumerate((height, height * 0.52)):
        pts = [(radius * math.cos(math.tau * i / segments),
                radius * math.sin(math.tau * i / segments),
                z + rz) for i in range(segments)]
        parts.append(add_curve_tube(f"{prefix}_Rail{ring_i}", pts, 0.035,
                                    mat, COL_KIT, cyclic=True, resolution_u=1,
                                    bevel_resolution=1))


def add_hip_roof(parts, prefix, width, depth, eave_z, rise, overhang,
                 mat_roof, mat_trim):
    """Curved hip roof as a closed shell with tile courses and hip ridges."""
    w = width + 2 * overhang
    d = depth + 2 * overhang
    lift = min(0.34, 0.045 * width)
    ridge_half = max(0.55, width * 0.14)
    A = Vector((-w / 2, -d / 2, eave_z + lift))
    B = Vector((w / 2, -d / 2, eave_z + lift))
    C = Vector((w / 2, d / 2, eave_z + lift))
    D = Vector((-w / 2, d / 2, eave_z + lift))
    E = Vector((-ridge_half, 0, eave_z + rise))
    F = Vector((ridge_half, 0, eave_z + rise))

    verts = []
    faces = []

    def add_quad_face(P0, P1, P2, P3, nu=10, nv=4):
        base = len(verts)
        for j in range(nv + 1):
            v = j / nv
            for i in range(nu + 1):
                u = i / nu
                q0 = P0.lerp(P1, u)
                q1 = P3.lerp(P2, u)
                p = q0.lerp(q1, v)
                corner = abs(u - 0.5) * 2.0
                p.z += lift * (1 - v) ** 2 * corner ** 3
                p.z -= 0.10 * math.sin(math.pi * v)
                verts.append((p.x, p.y, p.z))
        for j in range(nv):
            for i in range(nu):
                a = base + j * (nu + 1) + i
                b = a + 1
                c = a + nu + 2
                dd = a + nu + 1
                faces.append((a, b, c, dd))

    def add_tri_face(P0, P1, apex, nu=10, nv=4):
        base = len(verts)
        for j in range(nv):
            v = j / nv
            for i in range(nu + 1):
                u = i / nu
                p = P0.lerp(P1, u).lerp(apex, v)
                corner = abs(u - 0.5) * 2.0
                p.z += lift * (1 - v) ** 2 * corner ** 3
                p.z -= 0.10 * math.sin(math.pi * v)
                verts.append((p.x, p.y, p.z))
        apex_index = len(verts)
        verts.append((apex.x, apex.y, apex.z))
        for j in range(nv - 1):
            for i in range(nu):
                a = base + j * (nu + 1) + i
                b = a + 1
                c = a + nu + 2
                dd = a + nu + 1
                faces.append((a, b, c, dd))
        for i in range(nu):
            a = base + (nv - 1) * (nu + 1) + i
            b = a + 1
            faces.append((a, b, apex_index))

    add_quad_face(A, B, F, E)          # front
    add_quad_face(C, D, E, F)          # back
    add_tri_face(D, A, E)              # left
    add_tri_face(B, C, F)              # right

    roof = add_mesh_object(prefix + "_Roof", verts, faces, mat_roof, COL_KIT)
    add_solidify(roof, 0.12, 0.0)
    parts.append(roof)

    # Tile courses follow the slope lines.
    for face_index, (P0, P1, P2, P3) in enumerate(((A, B, F, E), (C, D, E, F))):
        for k, v in enumerate((0.18, 0.36, 0.54, 0.72, 0.88)):
            pts = []
            for i in range(13):
                u = i / 12
                q0 = P0.lerp(P1, u)
                q1 = P3.lerp(P2, u)
                p = q0.lerp(q1, v)
                p.z += lift * (1 - v) ** 2 * (abs(u - 0.5) * 2) ** 3 - 0.10 * math.sin(math.pi * v) + 0.075
                pts.append((p.x, p.y, p.z))
            parts.append(add_curve_tube(f"{prefix}_Tile_{face_index}_{k}", pts,
                                        0.016, mat_trim, COL_KIT, resolution_u=1,
                                        bevel_resolution=1))
    # Hip ridges and eave trim.
    for i, (a, b) in enumerate(((A, E), (B, F), (C, F), (D, E))):
        pts = []
        for t in range(6):
            p = a.lerp(b, t / 5)
            p.z += 0.06
            pts.append((p.x, p.y, p.z))
        parts.append(add_curve_tube(f"{prefix}_Hip_{i}", pts, 0.032, mat_trim,
                                    COL_KIT, resolution_u=1, bevel_resolution=1))
    for i, (a, b) in enumerate(((A, B), (B, C), (C, D), (D, A))):
        parts.append(add_curve_tube(f"{prefix}_Eave_{i}", [(a.x, a.y, a.z + 0.03),
                                                           (b.x, b.y, b.z + 0.03)],
                                    0.034, mat_trim, COL_KIT, resolution_u=1,
                                    bevel_resolution=1))
    # Ridge beam and end ornaments.
    parts.append(add_bar(f"{prefix}_RidgeBeam", (E.x, 0, E.z + 0.04),
                         (F.x, 0, F.z + 0.04), 0.10, mat_trim, COL_KIT))
    for sign, p in ((-1, E), (1, F)):
        parts.append(add_sphere(f"{prefix}_RidgeOrn_{sign}", 0.12,
                                (p.x, 0, p.z + 0.14), MAT_GOLD, COL_KIT,
                                segments=8, rings=4))
    # Eave tile ends (wadang) give the roofline a real edge instead of a slab.
    cap_z = eave_z + lift + 0.015
    add_eave_caps_x(parts, prefix + "_Front", -w / 2 + 0.1, w / 2 - 0.1,
                    -d / 2 - 0.02, cap_z, max(8, int(w / 0.38)), mat_trim)
    add_eave_caps_x(parts, prefix + "_Back", -w / 2 + 0.1, w / 2 - 0.1,
                    d / 2 + 0.02, cap_z, max(8, int(w / 0.38)), mat_trim)
    add_eave_caps_y(parts, prefix + "_Left", -d / 2 + 0.1, d / 2 - 0.1,
                    -w / 2 - 0.02, cap_z, max(8, int(d / 0.38)), mat_trim)
    add_eave_caps_y(parts, prefix + "_Right", -d / 2 + 0.1, d / 2 - 0.1,
                    w / 2 + 0.02, cap_z, max(8, int(d / 0.38)), mat_trim)
    # Upturned corner tips: the signature Jiangnan roof silhouette.
    for ci, (corner, sx, sy) in enumerate(((A, -1, -1), (B, 1, -1),
                                           (C, 1, 1), (D, -1, 1))):
        pts = [
            (corner.x, corner.y, corner.z + 0.02),
            (corner.x + sx * 0.16, corner.y + sy * 0.16, corner.z + 0.16),
            (corner.x + sx * 0.34, corner.y + sy * 0.34, corner.z + 0.42),
            (corner.x + sx * 0.46, corner.y + sy * 0.46, corner.z + 0.58),
        ]
        parts.append(add_curve_tube(f"{prefix}_Tip{ci}", pts, 0.055,
                                    mat_trim, COL_KIT, resolution_u=2,
                                    bevel_resolution=1))
        parts.append(add_sphere(f"{prefix}_TipOrn{ci}", 0.075,
                                (pts[-1][0], pts[-1][1], pts[-1][2] + 0.04),
                                MAT_GOLD, COL_KIT, segments=7, rings=4))
    return roof


def build_shophouse(name, width=8.0, depth=9.0, floors=2, variant=0):
    """Chinese river-town shophouse. Local facade faces -Y."""
    parts = []
    floor_h = 3.15
    base_h = 0.36
    body_h = floors * floor_h
    eave_z = base_h + body_h
    front_y = -depth / 2
    wall_mat = MAT_PLASTER if variant != 1 else MAT_PLASTER_2
    roof_mat = MAT_ROOF if variant != 2 else MAT_ROOF_2

    parts.append(add_box(f"{name}_Plinth", (width + 0.40, depth + 0.40, base_h),
                         (0, 0, base_h / 2), MAT_STONE, COL_KIT, bevel=0.04))
    parts.append(add_box(f"{name}_Body", (width, depth, body_h),
                         (0, 0, base_h + body_h / 2), wall_mat, COL_KIT))
    # Corner and intermediate timber columns on both facades.
    for x in (-width / 2 + 0.14, -width / 6, width / 6, width / 2 - 0.14):
        for y in (front_y - 0.02, -front_y + 0.02):
            parts.append(add_box(f"{name}_Col_{x:.1f}_{y:.1f}", (0.20, 0.22, body_h),
                                 (x, y, base_h + body_h / 2), MAT_WOOD, COL_KIT))
    # Floor bands.
    for f in range(floors):
        z = base_h + f * floor_h
        parts.append(add_box(f"{name}_Band_{f}", (width + 0.10, 0.18, 0.16),
                             (0, front_y - 0.04, z + 0.02), MAT_WOOD, COL_KIT))
        parts.append(add_box(f"{name}_BandBack_{f}", (width + 0.10, 0.18, 0.16),
                             (0, -front_y + 0.04, z + 0.02), MAT_WOOD, COL_KIT))
    # Ground-floor door and windows.
    door_w = min(1.5, width * 0.22)
    parts.append(add_box(f"{name}_DoorFrame", (door_w + 0.28, 0.16, 2.55),
                         (0, front_y - 0.05, base_h + 1.275), MAT_LACQUER, COL_KIT,
                         bevel=0.02))
    parts.append(add_box(f"{name}_Door", (door_w, 0.08, 2.25),
                         (0, front_y - 0.10, base_h + 1.125), MAT_WOOD_WARM, COL_KIT))
    for i in range(2):
        wx = (-1 if i == 0 else 1) * (width * 0.30)
        add_window(parts, f"{name}_W0_{i}", wx, base_h + 1.55,
                   min(1.55, width * 0.22), 1.65, front_y, outward=-1,
                   shutters=False, transom=True)
    # Stone threshold and a shallow step.
    parts.append(add_box(f"{name}_Step", (door_w + 0.9, 0.55, 0.14),
                         (0, front_y - 0.42, 0.07), MAT_STONE_LIGHT, COL_KIT,
                         bevel=0.02))
    # Upper-floor windows.
    for f in range(1, floors):
        zc = base_h + f * floor_h + floor_h * 0.52
        positions = (-width * 0.28, width * 0.28)
        if variant == 2:
            positions = (-width * 0.30, 0.0, width * 0.30)
        for i, wx in enumerate(positions):
            add_window(parts, f"{name}_W{f}_{i}", wx, zc,
                       min(1.35, width * 0.20), 1.45, front_y, outward=-1,
                       shutters=True, transom=True)
            add_window(parts, f"{name}_WB{f}_{i}", wx, zc,
                       min(1.25, width * 0.18), 1.35, -front_y, outward=1)
    # Gable windows so the house still reads when seen along the street.
    for f in range(floors):
        zc = base_h + f * floor_h + floor_h * 0.55
        for side in (-1, 1):
            for k, wy in enumerate((-depth * 0.22, depth * 0.22)):
                add_side_window(parts, f"{name}_SW{f}_{side}_{k}",
                                side * width / 2, wy, zc, min(1.1, depth * 0.16),
                                1.15, outward=side)
    # Balcony on the first upper floor.
    if variant == 1 and floors >= 2:
        z = base_h + floor_h
        parts.append(add_box(f"{name}_Balcony", (width * 0.94, 0.95, 0.16),
                             (0, front_y - 0.48, z - 0.02), MAT_WOOD, COL_KIT))
        for i in range(6):
            bx = -width * 0.40 + width * 0.80 * i / 5
            parts.append(add_box(f"{name}_BalPost_{i}", (0.07, 0.07, 0.90),
                                 (bx, front_y - 0.92, z + 0.45), MAT_LACQUER, COL_KIT))
        parts.append(add_bar(f"{name}_BalTop", (-width * 0.42, front_y - 0.92, z + 0.88),
                             (width * 0.42, front_y - 0.92, z + 0.88), 0.07,
                             MAT_LACQUER, COL_KIT))
        parts.append(add_bar(f"{name}_BalMid", (-width * 0.42, front_y - 0.92, z + 0.45),
                             (width * 0.42, front_y - 0.92, z + 0.45), 0.05,
                             MAT_WOOD, COL_KIT))
        for i in range(13):
            bx = -width * 0.40 + width * 0.80 * i / 12
            parts.append(add_box(f"{name}_Baluster_{i}", (0.035, 0.035, 0.40),
                                 (bx, front_y - 0.92, z + 0.22), MAT_LACQUER, COL_KIT))
    # Canvas awning over the shopfront, plus perpendicular hanging signs.
    add_shop_awning(parts, f"{name}_Awn", width, front_y, base_h + 2.98,
                    MAT_CLOTH_RED if variant != 1 else MAT_CLOTH_CREAM)
    for side in (-1, 1):
        add_shop_sign(parts, f"{name}_ShopSign{side}", side * width * 0.38,
                      front_y, base_h + 2.55, side)
    # Bracket sets carry the eave and break up the plaster field.
    add_dougong(parts, f"{name}_DG_F", width, front_y, eave_z,
                max(3, int(width / 1.6)), outward=-1)
    add_dougong(parts, f"{name}_DG_B", width, -front_y, eave_z,
                max(3, int(width / 1.6)), outward=1)
    # Signboard above the door.
    parts.append(add_box(f"{name}_SignBoard", (min(2.8, width * 0.40), 0.12, 0.55),
                         (0, front_y - 0.16, eave_z - 0.55), MAT_WOOD, COL_KIT,
                         bevel=0.02))
    parts.append(add_box(f"{name}_SignGold", (min(2.6, width * 0.36), 0.04, 0.09),
                         (0, front_y - 0.23, eave_z - 0.55), MAT_GOLD, COL_KIT))
    # Two hanging lanterns under the eave.
    for i, lx in enumerate((-width * 0.30, width * 0.30)):
        hook_z = eave_z - 0.12
        parts.append(add_cylinder(f"{name}_LanHook_{i}", 6, 0.015, 0.35,
                                  (lx, front_y - 0.28, hook_z), MAT_WOOD, COL_KIT))
        parts.append(add_sphere(f"{name}_LanBody_{i}", 0.22,
                                (lx, front_y - 0.28, hook_z - 0.42), MAT_PAPER_RED,
                                COL_KIT, segments=8, rings=4))
        parts.append(add_cylinder(f"{name}_LanCap_{i}", 8, 0.08, 0.05,
                                  (lx, front_y - 0.28, hook_z - 0.21), MAT_GOLD, COL_KIT))
    # Roof.
    add_hip_roof(parts, name, width, depth, eave_z, 2.0 + 0.18 * floors,
                 0.6, roof_mat, MAT_WOOD)
    obj = join_parts(parts, name)
    return finalize_kit(obj, name, 16000)


# ---------------------------------------------------------------------------
# Stone arch bridge
# ---------------------------------------------------------------------------

def deck_z(x, half=22.0):
    return 1.0 + 4.6 * math.cos(math.pi * x / (2 * half))


def arch_z(x, half=20.0):
    if abs(x) >= half:
        return 0.0
    return 5.0 * math.sqrt(max(0.0, 1.0 - (x / half) ** 2))


def build_bridge(name="SM_Env_Bridge_Arch_01", half=22.0, width=6.0):
    parts = []
    N = 20
    # Deck segments.
    for i in range(N):
        x0 = -half + 2 * half * i / N
        x1 = -half + 2 * half * (i + 1) / N
        z0, z1 = deck_z(x0, half), deck_z(x1, half)
        angle = -math.atan2(z1 - z0, x1 - x0)
        parts.append(add_box(f"{name}_Deck_{i:02d}",
                             (math.hypot(x1 - x0, z1 - z0) + 0.04, width, 0.40),
                             ((x0 + x1) / 2, 0, (z0 + z1) / 2 - 0.20),
                             MAT_STONE, COL_KIT, rotation=(0, angle, 0)))
    # Deck stone joints and a worn centre line.
    for i in range(N + 1):
        x = -half + 2 * half * i / N
        parts.append(add_box(f"{name}_Joint_{i:02d}", (0.055, width * 0.94, 0.41),
                             (x, 0, deck_z(x, half) - 0.20), MAT_STONE_LIGHT,
                             COL_KIT, bevel=0.006))
    # End steps down to the quay.
    for end in (-1, 1):
        for i in range(5):
            sx = end * (half + 0.28 + i * 0.30)
            parts.append(add_box(f"{name}_Step_{end}_{i}", (0.30, width, 0.20),
                                 (sx, 0, 0.90 - i * 0.18), MAT_STONE, COL_KIT))
    # Arch side ribbons.
    for side in (-1, 1):
        y0 = side * (width / 2 - 0.02)
        y1 = side * (width / 2 + 0.50)
        verts = []
        faces = []
        segments = 18
        for i in range(segments + 1):
            x = -20.0 + 40.0 * i / segments
            z_top = deck_z(x, half) - 0.42
            z_bot = arch_z(x)
            verts.extend([(x, y0, z_bot), (x, y0, z_top), (x, y1, z_bot), (x, y1, z_top)])
        for i in range(segments):
            a = i * 4
            b = (i + 1) * 4
            faces.append((a, b, b + 1, a + 1))          # inner face
            faces.append((a + 2, a + 3, b + 3, b + 2))  # outer face
            faces.append((a + 1, b + 1, b + 3, a + 3))  # top
            faces.append((a, a + 2, b + 2, b))          # bottom
        # End caps.
        faces.append((0, 1, 3, 2))
        last = segments * 4
        faces.append((last, last + 2, last + 3, last + 1))
        wall = add_mesh_object(f"{name}_ArchSide_{side}", verts, faces, MAT_STONE, COL_KIT)
        parts.append(wall)
    # Voussoir blocks around the arch face.
    for side in (-1, 1):
        for i in range(13):
            theta = math.pi * (i + 0.5) / 13.0
            x = 20.0 * math.cos(theta)
            z = 5.0 * math.sin(theta)
            rot = math.atan2(math.cos(theta), -math.sin(theta))
            parts.append(add_box(f"{name}_Voussoir_{side}_{i}",
                                 (0.85, 0.62, 0.45),
                                 (x, side * (width / 2 + 0.28), z),
                                 MAT_STONE_LIGHT, COL_KIT, rotation=(0, rot, 0),
                                 bevel=0.03))
    # Parapets and red railings.
    for side in (-1, 1):
        y = side * (width / 2 - 0.10)
        for i in range(N):
            x0 = -half + 2 * half * i / N
            x1 = -half + 2 * half * (i + 1) / N
            z0, z1 = deck_z(x0, half), deck_z(x1, half)
            angle = -math.atan2(z1 - z0, x1 - x0)
            parts.append(add_box(f"{name}_Parapet_{side}_{i:02d}",
                                 (math.hypot(x1 - x0, z1 - z0) + 0.02, 0.28, 0.55),
                                 ((x0 + x1) / 2, y, (z0 + z1) / 2 + 0.05),
                                 MAT_STONE, COL_KIT, rotation=(0, angle, 0)))
        # Posts and rails.
        for i in range(11):
            x = -half + 2 * half * i / 10
            z = deck_z(x, half) + 0.35
            parts.append(add_box(f"{name}_Post_{side}_{i}", (0.13, 0.13, 1.15),
                                 (x, y, z + 0.575), MAT_LACQUER, COL_KIT))
            parts.append(add_box(f"{name}_PostCap_{side}_{i}", (0.20, 0.20, 0.10),
                                 (x, y, z + 1.20), MAT_STONE_LIGHT, COL_KIT,
                                 bevel=0.02))
        # Carved balustrade panels between the posts.
        for i in range(10):
            x0 = -half + 2 * half * i / 10
            x1 = -half + 2 * half * (i + 1) / 10
            xm = (x0 + x1) / 2
            zm = (deck_z(x0, half) + deck_z(x1, half)) / 2 + 0.34
            ln = math.hypot(x1 - x0, deck_z(x1, half) - deck_z(x0, half))
            ang = -math.atan2(deck_z(x1, half) - deck_z(x0, half), x1 - x0)
            parts.append(add_box(f"{name}_BalPanel_{side}_{i}", (ln * 0.82, 0.08, 0.36),
                                 (xm, y + side * 0.02, zm), MAT_STONE_LIGHT,
                                 COL_KIT, rotation=(0, ang, 0), bevel=0.012))
            parts.append(add_box(f"{name}_BalInset_{side}_{i}", (ln * 0.58, 0.03, 0.22),
                                 (xm, y + side * 0.07, zm), MAT_STONE,
                                 COL_KIT, rotation=(0, ang, 0)))
        # Keystone on the arch face.
        parts.append(add_box(f"{name}_Keystone_{side}", (0.85, 0.78, 0.72),
                             (0, side * (width / 2 + 0.40), 5.02),
                             MAT_STONE_LIGHT, COL_KIT, bevel=0.03))
        for i in range(10):
            x0 = -half + 2 * half * i / 10
            x1 = -half + 2 * half * (i + 1) / 10
            z0 = deck_z(x0, half) + 1.30
            z1 = deck_z(x1, half) + 1.30
            parts.append(add_bar(f"{name}_RailTop_{side}_{i}", (x0, y, z0), (x1, y, z1),
                                 0.10, MAT_LACQUER, COL_KIT))
            parts.append(add_bar(f"{name}_RailMid_{side}_{i}", (x0, y, z0 - 0.42),
                                 (x1, y, z1 - 0.42), 0.06, MAT_WOOD, COL_KIT))
        # Four lantern posts.
        for i, x in enumerate((-half * 0.72, -half * 0.24, half * 0.24, half * 0.72)):
            z = deck_z(x, half) + 0.35
            parts.append(add_cylinder(f"{name}_LampPost_{side}_{i}", 6, 0.06, 2.0,
                                      (x, y, z + 1.0), MAT_WOOD, COL_KIT))
            parts.append(add_sphere(f"{name}_Lamp_{side}_{i}", 0.20,
                                    (x, y, z + 2.15), MAT_PAPER, COL_KIT,
                                    segments=8, rings=4))
    # Central plaque on the bridge side facing the camera.
    parts.append(add_box(f"{name}_Plaque", (2.8, 0.16, 0.75), (0, -width / 2 - 0.72, 4.3),
                         MAT_WOOD, COL_KIT, bevel=0.03))
    parts.append(add_box(f"{name}_PlaqueGold", (2.5, 0.05, 0.12), (0, -width / 2 - 0.81, 4.3),
                         MAT_GOLD, COL_KIT))
    obj = join_parts(parts, name)
    return finalize_kit(obj, name, 20000)


# ---------------------------------------------------------------------------
# Lantern tower (hero landmark)
# ---------------------------------------------------------------------------

def build_lantern_tower(name="SM_Env_LanternTower_01"):
    """Five-tier octagonal lantern tower with balconies, lattice bays and bells."""
    parts = []
    # Stone island: two stepped octagons and a carved railing.
    parts.append(add_cylinder(f"{name}_Island", 8, 6.4, 1.0, (0, 0, 0.5),
                              MAT_STONE, COL_KIT))
    parts.append(add_cylinder(f"{name}_IslandTop", 8, 5.8, 0.22, (0, 0, 1.08),
                              MAT_STONE_LIGHT, COL_KIT))
    parts.append(add_cylinder(f"{name}_IslandStep", 8, 6.7, 0.16, (0, 0, 0.08),
                              MAT_STONE_LIGHT, COL_KIT))
    for i in range(16):
        a = math.tau * i / 16
        parts.append(add_box(f"{name}_IslePost_{i}", (0.10, 0.10, 0.92),
                             (5.55 * math.cos(a), 5.55 * math.sin(a), 1.62),
                             MAT_STONE_LIGHT, COL_KIT, rotation=(0, 0, a)))
    for ri, rz in enumerate((2.08, 1.78)):
        pts = [(5.55 * math.cos(math.tau * i / 8), 5.55 * math.sin(math.tau * i / 8), rz)
               for i in range(8)]
        parts.append(add_curve_tube(f"{name}_IsleRail{ri}", pts, 0.055,
                                    MAT_STONE_LIGHT, COL_KIT, cyclic=True,
                                    resolution_u=1, bevel_resolution=1))
    # Watertight staircase protruding from the -Y edge of the island.
    parts.append(add_staircase(f"{name}_Stairs", 3.2, 4, 0.24, 0.25,
                               -7.35, 0.0, MAT_STONE, COL_KIT))
    for side in (-1, 1):
        x = side * 1.75
        pts = [(x, -7.4, 1.0), (x, -6.4, 1.55), (x, -5.6, 2.0)]
        parts.append(add_curve_tube(f"{name}_StairRail{side}", pts, 0.05,
                                    MAT_STONE_LIGHT, COL_KIT, resolution_u=1,
                                    bevel_resolution=1))
    tiers = [
        (4.6, 3.6, 1.45, 1.15),
        (3.9, 3.0, 1.25, 1.00),
        (3.2, 2.6, 1.10, 0.90),
        (2.6, 2.2, 0.95, 0.80),
        (2.0, 1.8, 0.85, 0.70),
    ]
    z = 1.2
    for ti, (radius, body_h, roof_rise, overhang) in enumerate(tiers):
        # Balcony ring under every upper tier.
        if ti > 0:
            balcony = add_cylinder(f"{name}_Balcony_{ti}", 8, radius + 0.62, 0.16,
                                   (0, 0, z - 0.02), MAT_WOOD, COL_KIT)
            parts.append(balcony)
            add_railing_ring(parts, f"{name}_BalR_{ti}", radius + 0.54, z + 0.06,
                             segments=8, post_count=16)
        # Body shell.
        parts.append(add_cylinder(f"{name}_Body_{ti}", 8, radius, body_h,
                                  (0, 0, z + body_h / 2), MAT_LACQUER, COL_KIT))
        # Eight recessed lattice bays per tier.
        face_width = 2.0 * radius * math.tan(math.pi / 8) * 0.70
        panel_h = body_h * 0.58
        for face in range(8):
            angle = 2 * math.pi * face / 8
            cx = (radius + 0.02) * math.cos(angle)
            cy = (radius + 0.02) * math.sin(angle)
            rot = angle + math.pi / 2
            parts.append(add_box(f"{name}_Pane_{ti}_{face}",
                                 (face_width, 0.035, panel_h),
                                 (cx, cy, z + body_h * 0.48),
                                 MAT_PAPER, COL_KIT, rotation=(0, 0, rot)))
            # Casing: two jambs, head and sill, all following the octagon face.
            for side in (-1, 1):
                ox = side * (face_width / 2 + 0.07)
                jx = cx + ox * math.cos(rot + math.pi / 2)
                jy = cy + ox * math.sin(rot + math.pi / 2)
                parts.append(add_box(f"{name}_BayJamb_{ti}_{face}_{side}",
                                     (0.10, 0.10, panel_h + 0.26),
                                     (jx, jy, z + body_h * 0.48),
                                     MAT_WOOD, COL_KIT, rotation=(0, 0, rot)))
            for dz, hh in ((panel_h / 2 + 0.10, 0.10), (-panel_h / 2 - 0.10, 0.09)):
                parts.append(add_box(f"{name}_BayRail_{ti}_{face}_{dz:.2f}",
                                     (face_width + 0.26, 0.12, hh),
                                     (cx, cy, z + body_h * 0.48 + dz),
                                     MAT_WOOD, COL_KIT, rotation=(0, 0, rot)))
            for b in range(4):
                offset = -face_width / 2 + face_width * (b + 1) / 5
                bx = cx + offset * math.cos(rot + math.pi / 2)
                by = cy + offset * math.sin(rot + math.pi / 2)
                parts.append(add_box(f"{name}_BarV_{ti}_{face}_{b}",
                                     (0.03, 0.045, panel_h),
                                     (bx, by, z + body_h * 0.48),
                                     MAT_WOOD, COL_KIT, rotation=(0, 0, rot)))
            for h in range(2):
                hz = z + body_h * 0.48 - panel_h / 2 + panel_h * (h + 1) / 3
                parts.append(add_box(f"{name}_BarH_{ti}_{face}_{h}",
                                     (face_width, 0.045, 0.03),
                                     (cx, cy, hz), MAT_WOOD, COL_KIT,
                                     rotation=(0, 0, rot)))
            # Small transom light above the bay.
            parts.append(add_box(f"{name}_Transom_{ti}_{face}",
                                 (face_width * 0.82, 0.03, 0.22),
                                 (cx, cy, z + body_h * 0.84),
                                 MAT_PAPER, COL_KIT, rotation=(0, 0, rot)))
        # Corner columns.
        for corner in range(8):
            angle = 2 * math.pi * (corner + 0.5) / 8
            cx = (radius + 0.10) * math.cos(angle)
            cy = (radius + 0.10) * math.sin(angle)
            parts.append(add_box(f"{name}_Col_{ti}_{corner}", (0.18, 0.18, body_h),
                                 (cx, cy, z + body_h / 2), MAT_WOOD, COL_KIT,
                                 rotation=(0, 0, angle)))
        eave_z = z + body_h
        # Bracket ring under the eave: beam ring plus stepped corner brackets.
        for bi, bz in enumerate((eave_z - 0.28, eave_z - 0.10)):
            pts = [((radius + 0.18) * math.cos(math.tau * i / 8),
                    (radius + 0.18) * math.sin(math.tau * i / 8), bz)
                   for i in range(8)]
            parts.append(add_curve_tube(f"{name}_BracketRing_{ti}_{bi}", pts,
                                        0.07, MAT_WOOD, COL_KIT, cyclic=True,
                                        resolution_u=1, bevel_resolution=1))
        for corner in range(8):
            angle = 2 * math.pi * (corner + 0.5) / 8
            cr, sr = math.cos(angle), math.sin(angle)
            for k, (rr, bz, sz) in enumerate((
                    (radius + 0.16, eave_z - 0.36, (0.34, 0.22, 0.10)),
                    (radius + 0.32, eave_z - 0.24, (0.24, 0.34, 0.10)),
                    (radius + 0.46, eave_z - 0.12, (0.16, 0.42, 0.09)))):
                parts.append(add_box(f"{name}_DG_{ti}_{corner}_{k}", sz,
                                     (rr * cr, rr * sr, bz),
                                     MAT_WOOD_WARM, COL_KIT,
                                     rotation=(0, 0, angle + math.pi / 2)))
        # Roof skirt.
        roof_profile = [
            (radius + overhang, eave_z),
            (radius + overhang * 0.72, eave_z + roof_rise * 0.36),
            (radius + overhang * 0.30, eave_z + roof_rise * 0.72),
            (radius * 0.92, eave_z + roof_rise),
        ]
        roof = add_lathe(f"{name}_Roof_{ti}", roof_profile, 8, MAT_ROOF, COL_KIT)
        add_solidify(roof, 0.10, 0.0)
        parts.append(roof)
        # Tile ridges on 8 hips.
        for corner in range(8):
            angle = 2 * math.pi * (corner + 0.5) / 8
            pts = []
            for k in range(5):
                t = k / 4
                rr = (radius + overhang) * (1 - t) + (radius * 0.92) * t
                zz = eave_z + roof_rise * (t ** 0.9) + 0.05
                pts.append((rr * math.cos(angle), rr * math.sin(angle), zz))
            parts.append(add_curve_tube(f"{name}_Hip_{ti}_{corner}", pts, 0.035,
                                        MAT_GOLD, COL_KIT, resolution_u=1,
                                        bevel_resolution=1))
        # Upturned eave tips and bells at 8 corners.
        for corner in range(8):
            angle = 2 * math.pi * (corner + 0.5) / 8
            er = radius + overhang
            ex, ey = er * math.cos(angle), er * math.sin(angle)
            pts = [(ex, ey, eave_z + 0.02),
                   (ex + 0.12 * math.cos(angle), ey + 0.12 * math.sin(angle), eave_z + 0.16),
                   (ex + 0.28 * math.cos(angle), ey + 0.28 * math.sin(angle), eave_z + 0.46)]
            parts.append(add_curve_tube(f"{name}_EaveTip_{ti}_{corner}", pts, 0.05,
                                        MAT_GOLD, COL_KIT, resolution_u=1,
                                        bevel_resolution=1))
            parts.append(add_sphere(f"{name}_EaveOrn_{ti}_{corner}", 0.07,
                                    (pts[-1][0], pts[-1][1], pts[-1][2] + 0.05),
                                    MAT_GOLD, COL_KIT, segments=7, rings=4))
            # Hanging bell with a red tassel.
            bx = (radius + overhang * 0.86) * math.cos(angle)
            by = (radius + overhang * 0.86) * math.sin(angle)
            parts.append(add_cylinder(f"{name}_Bell_{ti}_{corner}", 6, 0.06, 0.18,
                                      (bx, by, eave_z - 0.16), MAT_GOLD, COL_KIT))
            parts.append(add_sphere(f"{name}_BellClapper_{ti}_{corner}", 0.035,
                                    (bx, by, eave_z - 0.28), MAT_LACQUER, COL_KIT,
                                    segments=6, rings=3))
        z = eave_z + roof_rise
    # Finial: stacked base, rings and a slender spire.
    parts.append(add_cylinder(f"{name}_FinialBase", 8, 0.62, 0.38, (0, 0, z + 0.19),
                              MAT_GOLD, COL_KIT))
    parts.append(add_cylinder(f"{name}_FinialDrum", 8, 0.46, 0.30, (0, 0, z + 0.52),
                              MAT_LACQUER, COL_KIT))
    for i in range(4):
        parts.append(add_cylinder(f"{name}_FinialRing{i}", 8, 0.30 - i * 0.03, 0.06,
                                  (0, 0, z + 0.72 + i * 0.14), MAT_GOLD, COL_KIT))
    parts.append(add_cone(f"{name}_FinialCone", 8, 0.20, 0.02, 1.15,
                          (0, 0, z + 1.18), MAT_GOLD, COL_KIT))
    obj = join_parts(parts, name)
    return finalize_kit(obj, name, 55000)


# ---------------------------------------------------------------------------
# Market stall
# ---------------------------------------------------------------------------

def build_stall(name="SM_Prop_Stall_01", width=3.6, depth=2.6):
    parts = []
    h = 2.6
    parts.append(add_box(f"{name}_Counter", (width, 0.6, 0.9), (0, -depth / 2 + 0.3, 0.45),
                         MAT_WOOD, COL_KIT))
    parts.append(add_box(f"{name}_CounterTop", (width + 0.12, 0.72, 0.10),
                         (0, -depth / 2 + 0.3, 0.95), MAT_WOOD_WARM, COL_KIT))
    for x in (-width / 2 + 0.12, width / 2 - 0.12):
        for y in (-depth / 2 + 0.10, depth / 2 - 0.10):
            parts.append(add_box(f"{name}_Post_{x:.1f}_{y:.1f}", (0.12, 0.12, h),
                                 (x, y, h / 2), MAT_WOOD, COL_KIT))
    # Fabric awning, gently sloped.
    parts.append(add_box(f"{name}_Awning", (width + 0.55, depth + 0.35, 0.10),
                         (0, 0, h + 0.20), MAT_CLOTH_RED, COL_KIT,
                         rotation=(0.10, 0, 0)))
    parts.append(add_box(f"{name}_AwningTrim", (width + 0.60, 0.08, 0.28),
                         (0, -depth / 2 - 0.18, h + 0.06), MAT_CLOTH_CREAM, COL_KIT))
    # Hanging goods and lanterns.
    for i in range(3):
        x = -width * 0.30 + width * 0.30 * i
        parts.append(add_cylinder(f"{name}_Hang_{i}", 6, 0.012, 0.40,
                                  (x, -depth / 2 + 0.02, h - 0.10),
                                  MAT_WOOD, COL_KIT))
        parts.append(add_sphere(f"{name}_Lan_{i}", 0.14, (x, -depth / 2 + 0.02, h - 0.34),
                                MAT_PAPER_RED, COL_KIT, segments=8, rings=4))
    # Low shelves on the counter.
    for i in range(3):
        parts.append(add_box(f"{name}_Goods_{i}", (0.55, 0.40, 0.22),
                             (-width * 0.30 + width * 0.30 * i, -depth / 2 + 0.30, 1.10),
                             MAT_CLOTH_CREAM if i % 2 == 0 else MAT_LACQUER, COL_KIT))
    obj = join_parts(parts, name)
    return finalize_kit(obj, name, 5000)


# ---------------------------------------------------------------------------
# Pleasure boat (scene hero prop)
# ---------------------------------------------------------------------------

def build_pleasure_boat(name="SM_Prop_Boat_Pleasure_01"):
    """Jiangnan painted pleasure boat: curved sheer, cabin, tiled roof, lanterns."""
    parts = []
    stations = [
        (-5.6, 0.05, 1.05), (-4.8, 0.72, 0.88), (-3.4, 1.12, 0.70),
        (-1.6, 1.32, 0.60), (0.0, 1.38, 0.58), (1.6, 1.32, 0.60),
        (3.4, 1.12, 0.70), (4.8, 0.72, 0.88), (5.6, 0.05, 1.05),
    ]
    verts = []
    for y, hw, deck in stations:
        verts.extend([(-hw, y, 0.02), (-hw * 0.86, y, deck),
                      (hw * 0.86, y, deck), (hw, y, 0.02)])
    faces = []
    for i in range(len(stations) - 1):
        a = i * 4
        b = (i + 1) * 4
        faces.extend([(a, b, b + 1, a + 1), (a + 1, b + 1, b + 2, a + 2),
                      (a + 2, b + 2, b + 3, a + 3), (a, a + 3, b + 3, b)])
    faces.append((0, 1, 2, 3))
    last = (len(stations) - 1) * 4
    faces.append((last, last + 3, last + 2, last + 1))
    parts.append(add_mesh_object(name + "_Hull", verts, faces, MAT_WOOD_WARM, COL_KIT))
    # Red sheer strake follows the gunwale.
    for side in (-1, 1):
        pts = [(side * hw * 0.88, y, deck + 0.02) for y, hw, deck in stations]
        parts.append(add_curve_tube(f"{name}_Sheer_{side}", pts, 0.055,
                                    MAT_LACQUER, COL_KIT, resolution_u=2,
                                    bevel_resolution=1))
    # Deck planks.
    for i in range(9):
        y = -4.6 + i * 1.15
        parts.append(add_box(f"{name}_Plank_{i}", (2.1, 0.92, 0.05),
                             (0, y, 0.62), MAT_WOOD_WARM, COL_KIT, bevel=0.01))
    # Cabin.
    cabin_w, cabin_d, cabin_h = 2.55, 4.4, 1.55
    deck_z = 0.62
    parts.append(add_box(f"{name}_CabinFloor", (cabin_w + 0.3, cabin_d + 0.3, 0.12),
                         (0, 0, deck_z + 0.06), MAT_WOOD, COL_KIT))
    for sx in (-1, 1):
        parts.append(add_box(f"{name}_CabinSide_{sx}", (0.10, cabin_d, cabin_h),
                             (sx * cabin_w / 2, 0, deck_z + 0.12 + cabin_h / 2),
                             MAT_WOOD, COL_KIT))
    for sy in (-1, 1):
        parts.append(add_box(f"{name}_CabinEnd_{sy}", (cabin_w, 0.10, cabin_h),
                             (0, sy * cabin_d / 2, deck_z + 0.12 + cabin_h / 2),
                             MAT_LACQUER, COL_KIT))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(add_box(f"{name}_CabinPost_{sx}_{sy}", (0.13, 0.13, cabin_h),
                                 (sx * cabin_w / 2, sy * cabin_d / 2,
                                  deck_z + 0.12 + cabin_h / 2),
                                 MAT_WOOD, COL_KIT))
    # Cabin lattice windows.
    for side in (-1, 1):
        for k, wy in enumerate((-1.25, 1.25)):
            # Paper and lattice sit outside the solid wall; embedding them in
            # the wall thickness hides the emission completely in a night render.
            parts.append(add_box(f"{name}_CabPaper_{side}_{k}", (0.03, 1.15, 0.92),
                                 (side * (cabin_w / 2 + 0.075), wy,
                                  deck_z + 0.95), MAT_PAPER, COL_KIT))
            for i in range(3):
                by = wy - 1.15 / 2 + 1.15 * (i + 1) / 4
                parts.append(add_box(f"{name}_CabBarV_{side}_{k}_{i}", (0.05, 0.03, 0.92),
                                     (side * (cabin_w / 2 + 0.11), by, deck_z + 0.95),
                                     MAT_WOOD, COL_KIT))
            for j in range(2):
                bz = deck_z + 0.95 - 0.46 + 0.92 * (j + 1) / 3
                parts.append(add_box(f"{name}_CabBarH_{side}_{k}_{j}", (0.05, 1.15, 0.03),
                                     (side * (cabin_w / 2 + 0.11), wy, bz),
                                     MAT_WOOD, COL_KIT))
    # Cabin end windows face the bow and stern, the views the camera sees.
    for sy in (-1, 1):
        parts.append(add_box(f"{name}_CabEndPaper_{sy}", (1.15, 0.03, 0.82),
                             (0, sy * (cabin_d / 2 + 0.075), deck_z + 0.98),
                             MAT_PAPER, COL_KIT))
        for i in range(3):
            bx = -1.15 / 2 + 1.15 * (i + 1) / 4
            parts.append(add_box(f"{name}_CabEndBarV_{sy}_{i}", (0.03, 0.05, 0.82),
                                 (bx, sy * (cabin_d / 2 + 0.11), deck_z + 0.98),
                                 MAT_WOOD, COL_KIT))
        for j in range(2):
            bz = deck_z + 0.98 - 0.41 + 0.82 * (j + 1) / 3
            parts.append(add_box(f"{name}_CabEndBarH_{sy}_{j}", (1.15, 0.05, 0.03),
                                 (0, sy * (cabin_d / 2 + 0.11), bz),
                                 MAT_WOOD, COL_KIT))
    # Warm eave strip under the cabin roof: outlines the boat at night.
    roof_z = deck_z + 0.12 + cabin_h + 0.02
    for sy in (-1, 1):
        parts.append(add_box(f"{name}_EaveGlowEnd_{sy}", (cabin_w + 0.7, 0.06, 0.05),
                             (0, sy * (cabin_d / 2 + 0.36), roof_z),
                             MAT_PAPER_RED, COL_KIT))
    for sx in (-1, 1):
        parts.append(add_box(f"{name}_EaveGlowSide_{sx}", (0.06, cabin_d + 0.64, 0.05),
                             (sx * (cabin_w / 2 + 0.36), 0, roof_z),
                             MAT_PAPER_RED, COL_KIT))
    # Roof lanterns read as warm anchors against the dark water.
    for sy in (-1, 1):
        parts.append(add_cylinder(f"{name}_RoofLanWire_{sy}", 4, 0.012, 0.40,
                                  (0, sy * (cabin_d / 2 + 0.10), roof_z + 0.20),
                                  MAT_WOOD, COL_KIT))
        parts.append(add_sphere(f"{name}_RoofLan_{sy}", 0.19,
                                (0, sy * (cabin_d / 2 + 0.10), roof_z + 0.42),
                                MAT_PAPER_RED, COL_KIT, segments=8, rings=5))
        parts.append(add_cylinder(f"{name}_RoofLanCap_{sy}", 8, 0.07, 0.04,
                                  (0, sy * (cabin_d / 2 + 0.10), roof_z + 0.58),
                                  MAT_GOLD, COL_KIT))
    # Cabin roof.
    add_hip_roof(parts, name + "_CabinRoof", cabin_w, cabin_d,
                 deck_z + 0.12 + cabin_h, 0.78, 0.42, MAT_ROOF, MAT_WOOD)
    # Deck railing fore and aft.
    for yy in ((-4.9, -2.6), (2.6, 4.9)):
        for i in range(3):
            y = yy[0] + (yy[1] - yy[0]) * i / 2
            for side in (-1, 1):
                parts.append(add_box(f"{name}_RailPost_{yy[0]:.1f}_{i}_{side}",
                                     (0.06, 0.06, 0.72),
                                     (side * 1.05, y, deck_z + 0.36),
                                     MAT_LACQUER, COL_KIT))
        for side in (-1, 1):
            parts.append(add_bar(f"{name}_RailTop_{yy[0]:.1f}_{side}",
                                 (side * 1.05, yy[0], deck_z + 0.70),
                                 (side * 1.05, yy[1], deck_z + 0.70),
                                 0.05, MAT_LACQUER, COL_KIT))
    # Bow and stern lanterns on curved poles.
    for end in (-1, 1):
        y = end * 5.1
        parts.append(add_curve_tube(f"{name}_LanPole_{end}",
                                    [(0, y, deck_z), (0.55, y + end * 0.15, deck_z + 0.9),
                                     (0.9, y + end * 0.30, deck_z + 1.25)],
                                    0.035, MAT_WOOD, COL_KIT, resolution_u=1,
                                    bevel_resolution=1))
        parts.append(add_sphere(f"{name}_LanBody_{end}", 0.24,
                                (0.9, y + end * 0.30, deck_z + 1.02),
                                MAT_PAPER_RED, COL_KIT, segments=10, rings=6))
        parts.append(add_cylinder(f"{name}_LanCap_{end}", 8, 0.09, 0.05,
                                  (0.9, y + end * 0.30, deck_z + 1.24),
                                  MAT_GOLD, COL_KIT))
        parts.append(add_cylinder(f"{name}_LanTassel_{end}", 4, 0.03, 0.3,
                                  (0.9, y + end * 0.30, deck_z + 0.72),
                                  MAT_LACQUER, COL_KIT))
    # Oars stowed along the cabin.
    for side in (-1, 1):
        parts.append(add_bar(f"{name}_Oar_{side}",
                             (side * 1.6, -2.9, 0.85), (side * 3.6, 2.4, 0.62),
                             0.06, MAT_WOOD_WARM, COL_KIT))
    obj = join_parts(parts, name)
    return finalize_kit(obj, name, 20000)


# ---------------------------------------------------------------------------
# Build all pieces
# ---------------------------------------------------------------------------

built = []
built.append(build_shophouse("SM_Env_Shophouse_A_01", width=8.0, depth=9.0,
                             floors=2, variant=0))
built.append(build_shophouse("SM_Env_Shophouse_B_01", width=10.0, depth=10.0,
                             floors=3, variant=1))
built.append(build_shophouse("SM_Env_Shophouse_C_01", width=7.0, depth=8.5,
                             floors=2, variant=2))
built.append(build_bridge())
built.append(build_lantern_tower())
built.append(build_hung_lantern("SM_Prop_Lantern_Hung_01", scale=1.0))
built.append(build_sky_lantern("SM_Prop_Lantern_Sky_01"))
built.append(build_lantern_string("SM_Prop_LanternString_01", span=28.0,
                                  height=9.0, sag=1.8, spacing=1.4))
built.append(build_stall())
built.append(build_pleasure_boat())

# Move all kit pieces into COL_Export for validation/export.
for obj in list(COL_KIT.objects):
    if obj.type == "MESH":
        obj.select_set(True)
        move_to_collection(obj, COL_EXPORT)

# ---------------------------------------------------------------------------
# Save and export
# ---------------------------------------------------------------------------

KIT_BLEND = os.path.join(EXPORT_DIR, "SM_Env_LanternRiver_Kit.blend")
bpy.ops.wm.save_as_mainfile(filepath=KIT_BLEND)

report = {"kit": "SM_Env_LanternRiver_Kit", "pieces": [], "exports": {}}
for obj in sorted([o for o in COL_EXPORT.objects if o.type == "MESH"], key=lambda o: o.name):
    mesh = obj.data
    mesh.calc_loop_triangles()
    tris = len(mesh.loop_triangles)
    glb_path = os.path.join(KIT_DIR, obj.name + ".glb")
    fbx_path = os.path.join(KIT_DIR, obj.name + ".fbx")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=glb_path, export_format="GLB", use_selection=True,
        export_apply=True, export_yup=True, export_materials="EXPORT",
        export_texcoords=True, export_normals=True, export_cameras=False,
        export_lights=False)
    try:
        bpy.ops.export_scene.fbx(
            filepath=fbx_path, use_selection=True, object_types={"MESH"},
            apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
            apply_unit_scale=True, bake_anim=False, path_mode="AUTO")
        fbx_ok = True
    except Exception as exc:
        fbx_ok = False
        print("FBX_EXPORT_FAILED", obj.name, repr(exc))
    report["pieces"].append({
        "name": obj.name,
        "triangles": tris,
        "vertices": len(mesh.vertices),
        "materials": [slot.material.name for slot in obj.material_slots if slot.material],
        "dimensions_m": [round(v, 4) for v in obj.dimensions],
        "glb": glb_path,
        "fbx": fbx_path if fbx_ok else None,
    })
    print(f"[KIT] {obj.name}: {tris} tris, {len(mesh.vertices)} verts, "
          f"{len(obj.material_slots)} materials, dims={tuple(round(v, 3) for v in obj.dimensions)}")

report["kit_blend"] = KIT_BLEND
with open(os.path.join(REPORT_DIR, "kit_report.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=2)

print("KIT_REPORT_START")
print(json.dumps(report, ensure_ascii=False, indent=2))
print("KIT_REPORT_END")
