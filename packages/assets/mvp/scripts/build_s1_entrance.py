"""Build the S1 lantern-claiming station from the Shangyuan MVP PRD.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender -b --python-exit-code 1 \
        --python packages/assets/mvp/scripts/build_s1_entrance.py

The station is authored in metres, Z-up, with its pivot on the ground under the
table.  The GLB is exported Y-up through Blender's glTF exporter.  The hero
lantern keeps independently named parts so the runtime can animate the flame,
paper glow, outline and tassel without replacing the asset.
"""

import json
import math
import os
from pathlib import Path

import bpy
from mathutils import Vector


ASSET_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path("/Users/zjy/Downloads/抖音wowland 创作/wowland")
WEB_GLB = ROOT / "apps" / "web" / "public" / "models" / "mvp" / "s1-entrance.glb"
REPORT = ASSET_ROOT / "reports" / "s1-entrance-report.json"
TEXTURE_DIR = ASSET_ROOT / "textures"
PREVIEW = ASSET_ROOT / "preview" / "s1-entrance-preview.png"
for path in (WEB_GLB.parent, REPORT.parent, TEXTURE_DIR, PREVIEW.parent):
    path.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
scene.render.engine = "CYCLES"
scene.cycles.samples = 48
scene.render.resolution_x = 1200
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.view_settings.look = "AgX - Medium High Contrast"


def srgb(hex_value):
    value = hex_value.lstrip("#")
    out = []
    for index in (0, 2, 4):
        channel = int(value[index:index + 2], 16) / 255.0
        out.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def material(name, hex_base, metallic=0.0, roughness=0.5, emission=None,
             emission_strength=0.0, coat=0.0, sheen=0.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    base = srgb(hex_base)
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Coat Weight"].default_value = coat
    bsdf.inputs["Sheen Weight"].default_value = sheen
    bsdf.inputs["Alpha"].default_value = alpha
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*srgb(emission), 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = (*base, alpha)
    if alpha < 1.0:
        mat.surface_render_method = "DITHERED"
        mat.use_transparency_overlap = True
    return mat


WOOD = material("MAT_LR_Wood_Dark", "#33221C", roughness=0.42, coat=0.22)
WOOD_WARM = material("MAT_LR_Wood_Warm", "#4A2F20", roughness=0.46, coat=0.18)
LACQUER = material("MAT_LR_Lacquer_Red", "#A32E1B", roughness=0.38, coat=0.36)
GOLD = material("MAT_LR_Gold", "#D8B45A", metallic=0.95, roughness=0.26, coat=0.16)
PAPER_UNLIT = material("MAT_S1_Paper_Unlit", "#F3E6C8", roughness=0.62,
                       emission="#FFD9A0", emission_strength=0.08, sheen=0.18)
PAPER_GUIDE = material("MAT_S1_GuideLantern_Paper", "#E8D9B8", roughness=0.62,
                       emission="#FFC36A", emission_strength=0.02, sheen=0.18)
FLAME = material("MAT_S1_Flame", "#FFC46B", roughness=0.35,
                 emission="#FFB24A", emission_strength=0.9)
WICK = material("MAT_S1_Wick", "#231C16", roughness=0.9)
OUTLINE = material("MAT_S1_Outline", "#FFD470", roughness=0.25,
                   emission="#FFC45A", emission_strength=4.0, alpha=0.32)
STONE = material("MAT_LR_Stone", "#66626E", roughness=0.78)
PLASTER = material("MAT_LR_Plaster_Warm", "#E8DFCC", roughness=0.74)
GROUND_MARK = material("MAT_S1_GroundMark", "#D8B45A", roughness=0.7,
                       emission="#D8B45A", emission_strength=0.35, alpha=0.62)


def collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(col)
    return col


ROOT_COL = collection("COL_S1_Entrance")
TABLE_COL = collection("COL_S1_Table", ROOT_COL)
HERO_COL = collection("COL_S1_HeroLantern", ROOT_COL)
SIGN_COL = collection("COL_S1_Signs", ROOT_COL)
MARK_COL = collection("COL_S1_GroundMark", ROOT_COL)


def activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def move_to(obj, col):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    col.objects.link(obj)


def apply(obj):
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def box(name, size, location, mat, col, rotation=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    apply(obj)
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(40)
        activate(obj)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.data.materials.append(mat)
    move_to(obj, col)
    return obj


def cylinder(name, radius, depth, location, mat, col, vertices=24, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                        location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    apply(obj)
    obj.data.materials.append(mat)
    move_to(obj, col)
    return obj


def cone(name, radius1, radius2, depth, location, mat, col, vertices=16,
         rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1, radius2=radius2,
                                    depth=depth, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    apply(obj)
    obj.data.materials.append(mat)
    move_to(obj, col)
    return obj


def sphere(name, radius, location, mat, col, scale=(1, 1, 1), segments=20, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings,
                                         radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    apply(obj)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.materials.append(mat)
    move_to(obj, col)
    return obj


def bar(name, start, end, width, mat, col, depth=None):
    start, end = Vector(start), Vector(end)
    delta = end - start
    obj = box(name, (width, depth or width, delta.length), (start + end) / 2,
              mat, col)
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    apply(obj)
    return obj


def torus(name, major, minor, location, mat, col, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=24, minor_segments=8,
                                     location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    apply(obj)
    obj.data.materials.append(mat)
    move_to(obj, col)
    return obj


def empty(name, location, col):
    obj = bpy.data.objects.new(name, None)
    obj.location = location
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.12
    col.objects.link(obj)
    return obj


def parent_to(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def set_parent_keep_world(child, parent):
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


# ---------------------------------------------------------------------------
# A02 — Song-style keeper's table, deliberately restrained.
# ---------------------------------------------------------------------------
table_root = empty("S1_KeeperTable", (0, 0, 0), TABLE_COL)

table_top = box("S1_Table_Top", (1.86, 0.88, 0.09), (0, 0, 0.86), WOOD_WARM, TABLE_COL, bevel=0.025)
box("S1_Table_FrontApron", (1.70, 0.055, 0.16), (0, -0.39, 0.75), WOOD, TABLE_COL, bevel=0.012)
box("S1_Table_BackApron", (1.70, 0.055, 0.16), (0, 0.39, 0.75), WOOD, TABLE_COL, bevel=0.012)
box("S1_Table_LeftApron", (0.055, 0.70, 0.16), (-0.84, 0, 0.75), WOOD, TABLE_COL, bevel=0.012)
box("S1_Table_RightApron", (0.055, 0.70, 0.16), (0.84, 0, 0.75), WOOD, TABLE_COL, bevel=0.012)
for side in (-1, 1):
    for front in (-1, 1):
        cylinder(f"S1_Table_Leg_{side}_{front}", 0.055, 0.78,
                 (side * 0.79, front * 0.33, 0.39), WOOD, TABLE_COL, 12)
        box(f"S1_Table_Foot_{side}_{front}", (0.16, 0.16, 0.045),
            (side * 0.79, front * 0.33, 0.025), WOOD, TABLE_COL, bevel=0.008)
box("S1_Table_LowerShelf", (1.54, 0.60, 0.045), (0, 0, 0.28), WOOD, TABLE_COL, bevel=0.012)

# Hanging arm and a small brass finial; the lantern hangs just off centre.
box("S1_Table_Upright", (0.11, 0.13, 1.48), (-0.68, 0.12, 1.54), WOOD, TABLE_COL, bevel=0.015)
bar("S1_Table_ArmRake", (-0.67, 0.12, 2.24), (-0.30, 0.12, 2.34), 0.055, WOOD, TABLE_COL)
bar("S1_Table_Arm", (-0.67, 0.12, 2.34), (0.12, 0.12, 2.34), 0.07, WOOD_WARM, TABLE_COL)
cone("S1_Table_ArmFinial", 0.09, 0.0, 0.16, (0.16, 0.12, 2.34), GOLD, TABLE_COL,
     rotation=(0, math.pi / 2, 0))
torus("S1_Table_ArmRing", 0.065, 0.013, (0.04, 0.12, 2.33), GOLD, TABLE_COL,
      rotation=(math.pi / 2, 0, 0))

# Table props stay smaller and dimmer than the hero lantern.
cylinder("S1_Table_OilDish", 0.105, 0.035, (-0.58, -0.23, 0.925), LACQUER, TABLE_COL, 20)
sphere("S1_Table_OilFlame", 0.026, (-0.58, -0.23, 0.965), FLAME, TABLE_COL,
       scale=(0.7, 0.7, 1.6), segments=12, rings=8)
cylinder("S1_Table_BambooHolder", 0.095, 0.22, (0.66, -0.20, 1.02), WOOD_WARM, TABLE_COL, 16)
for index in range(4):
    angle = index * math.tau / 4
    bar(f"S1_Table_BambooSlip_{index}",
        (0.66 + math.cos(angle) * 0.025, -0.20 + math.sin(angle) * 0.025, 1.11),
        (0.66 + math.cos(angle) * 0.018, -0.20 + math.sin(angle) * 0.018, 1.36),
        0.014, PLASTER, TABLE_COL)
box("S1_Table_BrassWeight", (0.22, 0.11, 0.045), (0.47, 0.21, 0.93), GOLD, TABLE_COL, bevel=0.01)

for obj in TABLE_COL.objects:
    if obj.type == "MESH":
        set_parent_keep_world(obj, table_root)


# ---------------------------------------------------------------------------
# A03 — independently controllable hero paper lantern.
# ---------------------------------------------------------------------------
hero_root = empty("S1_HeroLantern", (0.04, 0.12, 0), HERO_COL)
frame_root = empty("S1_HeroLantern_Frame", (0, 0, 0), HERO_COL)
paper_root = empty("S1_HeroLantern_Paper", (0, 0, 0), HERO_COL)
wick_root = empty("S1_HeroLantern_Wick", (0, 0, -0.06), HERO_COL)
flame_root = empty("S1_HeroLantern_Flame", (0, 0, -0.035), HERO_COL)
tassel_root = empty("S1_HeroLantern_Tassel", (0, 0, -0.69), HERO_COL)
outline_root = empty("S1_HeroLantern_Outline", (0, 0, 0), HERO_COL)

hero_root.location = (0.04, 0.12, 0)
for part in (frame_root, paper_root, wick_root, flame_root, tassel_root, outline_root):
    part.parent = hero_root

# Hanger from the arm down into the lantern crown.
bar("S1_HeroLantern_HangerTop", (0, 0, 0.66), (0, 0, 0.50), 0.018, GOLD, HERO_COL)
torus("S1_HeroLantern_HangerLoop", 0.055, 0.012, (0, 0, 0.66), GOLD, HERO_COL,
      rotation=(math.pi / 2, 0, 0))

# Deep wooden frame: crown, skirt, four ribs and four corner posts.
cylinder("S1_HeroLantern_Crown", 0.27, 0.045, (0, 0, 0.47), WOOD, HERO_COL, 16)
cylinder("S1_HeroLantern_Skirt", 0.34, 0.05, (0, 0, -0.50), WOOD, HERO_COL, 16)
torus("S1_HeroLantern_CrownRing", 0.28, 0.018, (0, 0, 0.44), GOLD, HERO_COL,
      rotation=(math.pi / 2, 0, 0))
torus("S1_HeroLantern_SkirtRing", 0.35, 0.02, (0, 0, -0.47), GOLD, HERO_COL,
      rotation=(math.pi / 2, 0, 0))
for index, angle in enumerate((math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4)):
    x = math.cos(angle) * 0.32
    y = math.sin(angle) * 0.32
    bar(f"S1_HeroLantern_Post_{index}", (x * 0.82, y * 0.82, 0.44),
        (x, y, -0.47), 0.028, LACQUER, HERO_COL)

# Six-sided warm-white paper body.  Slight vertical bulge avoids a flat cylinder.
vertices = []
faces = []
sides = 12
levels = (0.41, 0.22, 0.0, -0.22, -0.43)
radii = (0.255, 0.34, 0.375, 0.34, 0.255)
for level_index, (level_z, radius) in enumerate(zip(levels, radii)):
    for side in range(sides):
        angle = side * math.tau / sides
        vertices.append((math.cos(angle) * radius, math.sin(angle) * radius, level_z))
for level_index in range(len(levels) - 1):
    for side in range(sides):
        next_side = (side + 1) % sides
        lower = level_index * sides
        upper = (level_index + 1) * sides
        faces.append((lower + side, lower + next_side, upper + next_side, upper + side))

paper_mesh = bpy.data.meshes.new("S1_HeroLantern_PaperMesh")
paper_mesh.from_pydata(vertices, [], faces)
paper_mesh.update()
paper_mesh.materials.append(PAPER_UNLIT)
paper_obj = bpy.data.objects.new("S1_HeroLantern_PaperMesh", paper_mesh)
HERO_COL.objects.link(paper_obj)
for poly in paper_obj.data.polygons:
    poly.use_smooth = True
    poly.material_index = 0

# A soft vermilion seal on two faces reads as a Chinese paper lantern.
seal_mat = material("MAT_S1_Seal", "#B23A24", roughness=0.55, emission="#B23A24", emission_strength=0.15)
for side, angle in enumerate((0, math.pi)):
    radius = 0.383
    seal = box(f"S1_HeroLantern_Seal_{side}", (0.13, 0.008, 0.18),
               (math.cos(angle) * radius, math.sin(angle) * radius, -0.02),
               seal_mat, HERO_COL, rotation=(0, 0, 0))
    seal.rotation_euler.z = angle + math.pi / 2

# Outline shell: slightly larger, transparent, hidden by default in runtime.
outline_mesh = paper_mesh.copy()
outline_mesh.name = "S1_HeroLantern_OutlineMesh"
outline_mesh.materials.clear()
outline_mesh.materials.append(OUTLINE)
outline_obj = bpy.data.objects.new("S1_HeroLantern_OutlineMesh", outline_mesh)
HERO_COL.objects.link(outline_obj)
outline_obj.scale = (1.045, 1.045, 1.035)
outline_obj.hide_render = False
outline_obj.hide_viewport = False
for _polygon in outline_obj.data.polygons:
    _polygon.use_smooth = False

# Wick, tiny initial flame and a five-strand tassel.
cylinder("S1_HeroLantern_WickMesh", 0.014, 0.12, (0, 0, 0.005), WICK, HERO_COL, 10)
flame = sphere("S1_HeroLantern_FlameMesh", 0.055, (0, 0, 0.075), FLAME, HERO_COL,
               scale=(0.55, 0.55, 1.5), segments=14, rings=9)
flame.scale = (0.16, 0.16, 0.22)
cone("S1_HeroLantern_TasselCap", 0.07, 0.035, 0.10, (0, 0, -0.03), GOLD, HERO_COL, 12)
for index in range(5):
    angle = index * math.tau / 5
    bar(f"S1_HeroLantern_TasselStrand_{index}",
        (math.cos(angle) * 0.018, math.sin(angle) * 0.018, -0.06),
        (math.cos(angle) * 0.026, math.sin(angle) * 0.026, -0.30),
        0.011, LACQUER, HERO_COL)

hero_parts = {
    "S1_HeroLantern_Frame": [
        "S1_HeroLantern_HangerTop", "S1_HeroLantern_HangerLoop", "S1_HeroLantern_Crown",
        "S1_HeroLantern_Skirt", "S1_HeroLantern_CrownRing", "S1_HeroLantern_SkirtRing",
    ] + [f"S1_HeroLantern_Post_{index}" for index in range(4)],
    "S1_HeroLantern_Paper": ["S1_HeroLantern_PaperMesh", "S1_HeroLantern_Seal_0", "S1_HeroLantern_Seal_1"],
    "S1_HeroLantern_Wick": ["S1_HeroLantern_WickMesh"],
    "S1_HeroLantern_Flame": ["S1_HeroLantern_FlameMesh"],
    "S1_HeroLantern_Tassel": ["S1_HeroLantern_TasselCap"] + [
        f"S1_HeroLantern_TasselStrand_{index}" for index in range(5)
    ],
    "S1_HeroLantern_Outline": ["S1_HeroLantern_OutlineMesh"],
}
for root_name, part_names in hero_parts.items():
    root = bpy.data.objects[root_name]
    for part_name in part_names:
        set_parent_keep_world(bpy.data.objects[part_name], root)


# ---------------------------------------------------------------------------
# A05 — high-contrast Chinese signs with embedded textures.
# ---------------------------------------------------------------------------
def find_font():
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/System/Library/Fonts/Supplemental/Kailasa.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


FONT_PATH = find_font()


def set_front_uv(obj):
    mesh = obj.data
    uv = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    mesh.uv_layers.active = uv
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv.data[loop_index].uv = (0.5 + vertex.x, vertex.z + 0.5)


def load_sign_material(name, filename):
    image_path = TEXTURE_DIR / filename
    image = bpy.data.images.load(str(image_path), check_existing=True)
    image.colorspace_settings.name = "sRGB"
    mat = material(name, "#FFFFFF", roughness=0.7)
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    nodes.active = tex
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.1
    bsdf.inputs["Roughness"].default_value = 0.82
    return mat


sign_mat = load_sign_material("T_S1_LingDengRuShi", "T_S1_LingDengRuShi.png")
way_mat = load_sign_material("T_S1_Wayfinder", "T_S1_Wayfinder.png")

sign_main = empty("S1_Sign_Main", (0, 0, 0), SIGN_COL)
sign_way = empty("S1_Sign_Wayfinder", (0, 0, 0), SIGN_COL)

# Main plaque hangs from the table arm on the approach-facing side.
box("S1_Sign_MainFrame", (1.42, 0.10, 0.49), (-0.34, -0.28, 2.86), WOOD, SIGN_COL, bevel=0.018)
main_face = box("S1_Sign_MainFace", (1.32, 0.02, 0.39), (-0.34, -0.352, 2.86),
                sign_mat, SIGN_COL, bevel=0.006)
set_front_uv(main_face)
for side in (-1, 1):
    cylinder(f"S1_Sign_MainStud_{side}", 0.025, 0.03,
             (-0.34 + side * 0.56, -0.36, 2.86), GOLD, SIGN_COL, 12,
             rotation=(math.pi / 2, 0, 0))

# A second, smaller wayfinder points toward the riddle market (+Y in Blender).
box("S1_Sign_WayPost", (0.11, 0.11, 1.72), (0.82, 0.62, 0.86), WOOD, SIGN_COL, bevel=0.014)
box("S1_Sign_WayFrame", (1.28, 0.09, 0.40), (0.82, 0.62, 1.62), WOOD, SIGN_COL, bevel=0.015)
way_face = box("S1_Sign_WayFace", (1.20, 0.018, 0.32), (0.82, 0.548, 1.62),
               way_mat, SIGN_COL, bevel=0.005)
guide_root = empty("S1_GuideLantern", (1.36, 0.62, 1.53), SIGN_COL)
set_front_uv(way_face)
cone("S1_Sign_WayLanternCap", 0.13, 0.07, 0.16, (1.36, 0.62, 1.68), LACQUER, SIGN_COL)
guide_paper = sphere("S1_GuideLantern_Paper", 0.11, (1.36, 0.62, 1.53), PAPER_GUIDE, SIGN_COL,
                     scale=(1, 1, 1.22), segments=16, rings=10)
torus("S1_GuideLantern_Ring", 0.10, 0.012, (1.36, 0.62, 1.63), GOLD, SIGN_COL,
      rotation=(math.pi / 2, 0, 0))

for child_name in (
    "S1_Sign_MainFrame", "S1_Sign_MainFace", "S1_Sign_MainStud_-1", "S1_Sign_MainStud_1",
):
    set_parent_keep_world(bpy.data.objects[child_name], sign_main)
for child_name in (
    "S1_Sign_WayPost", "S1_Sign_WayFrame", "S1_Sign_WayFace", "S1_Sign_WayLanternCap",
    "S1_GuideLantern_Ring",
):
    set_parent_keep_world(bpy.data.objects[child_name], sign_way)
set_parent_keep_world(guide_root, sign_way)
set_parent_keep_world(guide_paper, guide_root)


# ---------------------------------------------------------------------------
# P01 — subtle floor marker, raised 3 cm to avoid z-fighting.
# ---------------------------------------------------------------------------
mark_root = empty("S1_P01_GroundMarker", (0, -0.92, 0.03), MARK_COL)
torus("S1_P01_MarkerRing", 0.78, 0.018, (0, -0.92, 0.031), GROUND_MARK, MARK_COL)
for petal in range(8):
    angle = petal * math.tau / 8
    sphere(f"S1_P01_LotusPetal_{petal}", 0.13,
           (math.cos(angle) * 0.48, -0.92 + math.sin(angle) * 0.48, 0.032),
           GROUND_MARK, MARK_COL, scale=(0.42, 1.0, 0.025), segments=12, rings=6
           ).rotation_euler.z = angle
cylinder("S1_P01_MarkerCore", 0.12, 0.01, (0, -0.92, 0.035), GROUND_MARK, MARK_COL, 16)


for obj in scene.objects:
    if obj.name.startswith("S1_HeroLantern_"):
        obj.location.z += 0.85

# Station signboards and marker belong to the same movable asset.
for obj in list(SIGN_COL.objects) + list(MARK_COL.objects):
    if obj.type == "MESH":
        set_parent_keep_world(obj, table_root)


# Camera and light strictly for the preview; excluded from the GLB export.
preview_col = collection("COL_S1_PreviewOnly")
camera_data = bpy.data.cameras.new("Camera_S1_Preview")
camera = bpy.data.objects.new("Camera_S1_Preview", camera_data)
preview_col.objects.link(camera)
camera.location = (3.5, -5.4, 3.1)
target = Vector((0, 0, 1.25))
direction = target - camera.location
camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
camera_data.lens = 38
scene.camera = camera

for name, location, energy, color, size in (
    ("KEY", (2.2, -3.8, 5.0), 620, (1.0, 0.78, 0.52), 4.0),
    ("FILL", (-3.2, -1.4, 3.0), 340, (0.55, 0.7, 1.0), 3.5),
    ("RIM", (0.8, 3.0, 3.6), 460, (1.0, 0.54, 0.28), 2.0),
):
    data = bpy.data.lights.new(f"LIGHT_S1_{name}", "AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(f"LIGHT_S1_{name}", data)
    preview_col.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (target - Vector(location)).to_track_quat("-Z", "Y").to_euler()

ground = box("PREVIEW_Ground", (7, 7, 0.04), (0, 0, -0.03), STONE, preview_col)
ground.hide_render = False

scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)



# Report before export so the numbers describe the authored source.
def object_metrics(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return {
        "min": [round(min(corner[axis] for corner in corners), 4) for axis in range(3)],
        "max": [round(max(corner[axis] for corner in corners), 4) for axis in range(3)],
    }


export_objects = [
    obj for obj in scene.objects
    if obj.type == "MESH" and not any(col.name == "COL_S1_PreviewOnly" for col in obj.users_collection)
]
triangles = 0
vertices = 0
for obj in export_objects:
    mesh = obj.data
    vertices += len(mesh.vertices)
    triangles += sum(len(poly.vertices) - 2 for poly in mesh.polygons)

all_corners = [obj.matrix_world @ Vector(corner) for obj in export_objects for corner in obj.bound_box]
bounds = {
    "min": [round(min(corner[axis] for corner in all_corners), 4) for axis in range(3)],
    "max": [round(max(corner[axis] for corner in all_corners), 4) for axis in range(3)],
}

report = {
    "asset_id": "S1-Entrance",
    "version": "1.0.0",
    "source": "packages/assets/mvp/scripts/build_s1_entrance.py",
    "runtime_glb": "apps/web/public/models/mvp/s1-entrance.glb",
    "axes": "authored Z-up metres; exported glTF Y-up with applied transforms",
    "pivot": "ground under the keeper table",
    "bounds_m": bounds,
    "dimensions_m": [round(bounds["max"][axis] - bounds["min"][axis], 4) for axis in range(3)],
    "triangles": triangles,
    "vertices": vertices,
    "textures": [str(path.relative_to(ROOT)) for path in sorted(TEXTURE_DIR.glob("*.png"))],
    "hero_parts": {
        name: [part.name for part in bpy.data.objects[name].children]
        for name in hero_parts
    },
    "named_groups": ["S1_Sign_Main", "S1_Sign_Wayfinder", "S1_GuideLantern"],
    "hero_part_bounds": {
        name: object_metrics(bpy.data.objects[name]) for name in hero_parts
    },
    "recommended_collision": {
        "table": {"center": [0, 0, 0.45], "size": [1.9, 0.92, 0.9]},
        "upright": {"center": [-0.68, 0.12, 0.8], "size": [0.14, 0.16, 1.6]},
        "sign_post": {"center": [0.82, 0.62, 0.86], "size": [0.14, 0.14, 1.72]},
    },
    "export": {
        "recommended_runtime_root_rotation_y": 0.0,
        "format": "GLB",
        "export_yup": True,
        "apply_transforms": True,
        "materials": "exported with embedded image textures",
    },
    "notes": [
        "Hero lantern is unlit by default; runtime animates FLAME scale and PAPER emission.",
        "Outline mesh is hidden by default and should become visible on proximity highlight.",
        "S1_GuideLantern is off by default; runtime raises MAT_S1_GuideLantern_Paper emission after claiming.",
        "Preview-only camera, lights and ground are excluded from the GLB.",
    ],
}
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

bpy.ops.object.select_all(action="DESELECT")
for obj in export_objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = table_root
bpy.ops.export_scene.gltf(
    filepath=str(WEB_GLB),
    export_format="GLB",
    use_selection=True,
    export_yup=True,
    export_apply=False,
    export_materials="EXPORT",
    export_image_format="AUTO",
    export_cameras=False,
    export_lights=False,
    export_animations=False,
)

source_blend = ASSET_ROOT / "exports" / "S1_Entrance.blend"
source_blend.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(source_blend))

print("S1_ASSET_REPORT", json.dumps({
    "glb": str(WEB_GLB),
    "glb_bytes": WEB_GLB.stat().st_size,
    "preview": str(PREVIEW),
    "report": str(REPORT),
    "triangles": triangles,
    "bounds": bounds,
    "hero_parts": list(hero_parts),
    "named_groups": ["S1_Sign_Main", "S1_Sign_Wayfinder", "S1_GuideLantern"],
}, ensure_ascii=False))
