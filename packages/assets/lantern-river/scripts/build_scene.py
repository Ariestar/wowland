"""Build the Lantern River night lookdev scene from the modular kit.

Run:
    blender -b --python assets/lantern-river/scripts/build_scene.py
Optional env:
    LR_FAST=1        half resolution / 32 samples preview render
    LR_SKIP_RENDER=1 build and save only

Outputs:
    assets/lantern-river/exports/SM_Scene_LanternRiver_Night.blend
    assets/lantern-river/renders/raw/*.png
    assets/lantern-river/reports/scene_report.json
"""

import bpy
import bmesh
import json
import math
import os
import random
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.dirname(HERE)
FOLIAGE_DIR = os.path.join(ASSET_DIR, "textures")
EXPORT_DIR = os.path.join(ASSET_DIR, "exports")
RENDER_DIR = os.path.join(ASSET_DIR, "renders", "raw")
REPORT_DIR = os.path.join(ASSET_DIR, "reports")
KIT_BLEND = os.path.join(EXPORT_DIR, "SM_Env_LanternRiver_Kit.blend")
PAVILION_BLEND = os.path.join(os.path.dirname(ASSET_DIR), "pavilion", "exports",
                              "SM_Env_Pavilion_Hex_01.blend")
LANTERN_BLEND = os.path.join(os.path.dirname(ASSET_DIR), "lantern", "exports",
                             "SM_PalaceLantern_6S.blend")
for path in (RENDER_DIR, REPORT_DIR):
    os.makedirs(path, exist_ok=True)

FAST = os.environ.get("LR_FAST") == "1"
SKIP_RENDER = os.environ.get("LR_SKIP_RENDER") == "1"
SEED = 20261118
random.seed(SEED)

bpy.ops.wm.open_mainfile(filepath=KIT_BLEND)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0

# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    if parent:
        parent.children.link(col)
    else:
        scene.collection.children.link(col)
    return col

COL_ROOT = new_collection("COL_LanternRiver_Scene")
COL_ENV = new_collection("COL_Environment", COL_ROOT)
COL_BANKS = new_collection("COL_Banks", COL_ROOT)
COL_BUILDINGS = new_collection("COL_Buildings", COL_ROOT)
COL_LANDMARKS = new_collection("COL_Landmarks", COL_ROOT)
COL_PROPS = new_collection("COL_Props", COL_ROOT)
COL_TREES = new_collection("COL_Trees", COL_ROOT)
COL_SKY = new_collection("COL_Sky", COL_ROOT)
COL_FX = new_collection("COL_FX", COL_ROOT)
COL_LIGHTS = new_collection("COL_Lights", COL_ROOT)
COL_CAMERAS = new_collection("COL_Cameras", COL_ROOT)

# Keep the kit master objects out of the render; duplicates share their meshes.
for obj in list(bpy.data.objects):
    if obj.name.startswith(("SM_Env_Shophouse", "SM_Env_Bridge", "SM_Env_LanternTower",
                            "SM_Prop_Lantern", "SM_Prop_Stall")):
        obj.hide_render = True
        obj.hide_set(True)

# ---------------------------------------------------------------------------
# Material helpers
# ---------------------------------------------------------------------------

def srgb(hex_value):
    value = hex_value.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(value[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def principled(name, hex_base, roughness=0.5, metallic=0.0, emission=None,
               emission_strength=0.0, coat=0.0, bump=0.0, bump_scale=12.0,
               alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*srgb(hex_base), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Coat Weight"].default_value = coat
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*srgb(emission), 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.surface_render_method = "DITHERED"
    if bump > 0:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = bump_scale
        tex.inputs["Detail"].default_value = 3.0
        bmp = nt.nodes.new("ShaderNodeBump")
        bmp.inputs["Strength"].default_value = bump
        bmp.inputs["Distance"].default_value = 0.08
        nt.links.new(tex.outputs["Fac"], bmp.inputs["Height"])
        nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    mat.diffuse_color = (*srgb(hex_base), alpha)
    return mat


def card_material(name, atlas, glow, glow_strength):
    """A double-sided alpha-cut foliage card.

    The atlas holds four clusters in a 2 x 2 grid; every card picks one tile in
    its UVs, so a whole canopy needs one material and one draw call.  The same
    image drives emission, which keeps the blossoms glowing in their own colours
    instead of washing out to a flat pink.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Emission Strength"].default_value = glow_strength
    bsdf.inputs["Emission Color"].default_value = (*srgb(glow), 1.0)

    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    image = bpy.data.images.load(os.path.join(FOLIAGE_DIR, atlas), check_existing=True)
    image.colorspace_settings.name = "sRGB"
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.extension = "CLIP"
    tex.interpolation = "Linear"
    nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])

    mat.blend_method = "CLIP"
    mat.alpha_threshold = 0.5
    mat.use_backface_culling = False
    return mat


# Rendered from 3D clusters by scripts/make_foliage_atlas.py.
MAT_BLOSSOM_CARD = card_material("MAT_SCENE_BlossomCard", "blossom_atlas.png",
                                 "#FFC2D8", 0.55)
MAT_WILLOW_CARD = card_material("MAT_SCENE_WillowCard", "willow_atlas.png",
                                "#A8CC78", 0.16)
MAT_SHRUB_CARD = card_material("MAT_SCENE_ShrubCard", "shrub_atlas.png",
                               "#9DBE6A", 0.12)


def emission_material(name, hex_color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*srgb(hex_color), 1.0)
    emit.inputs["Strength"].default_value = strength
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def paving_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.64
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Scale"].default_value = 0.8
    brick.inputs["Mortar Size"].default_value = 0.012
    brick.inputs["Brick Width"].default_value = 0.72
    brick.inputs["Row Height"].default_value = 0.36
    brick.inputs["Color1"].default_value = (*srgb("#5A5863"), 1)
    brick.inputs["Color2"].default_value = (*srgb("#6A6672"), 1)
    brick.inputs["Mortar"].default_value = (*srgb("#34323C"), 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.05
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(brick.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def water_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*srgb("#0A1230"), 1)
    bsdf.inputs["Metallic"].default_value = 0.28
    bsdf.inputs["Roughness"].default_value = 0.07
    bsdf.inputs["IOR"].default_value = 1.33
    bsdf.inputs["Coat Weight"].default_value = 0.55
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 0.35
    tex.inputs["Detail"].default_value = 5.0
    tex.inputs["Roughness"].default_value = 0.55
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.09
    bump.inputs["Distance"].default_value = 0.10
    nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


MAT_PAVING = paving_material("MAT_SCENE_Paving")
MAT_QUAY = principled("MAT_SCENE_QuayStone", "#55515E", roughness=0.8, bump=0.2, bump_scale=12)
MAT_WATER = water_material("MAT_SCENE_Water")
MAT_MOUNTAIN_FAR = principled("MAT_SCENE_MountainFar", "#121A3E", roughness=0.9,
                              emission="#1A2450", emission_strength=0.10)
MAT_MOUNTAIN_NEAR = principled("MAT_SCENE_MountainNear", "#080D22", roughness=0.9,
                               emission="#101838", emission_strength=0.05)
MAT_STAR = emission_material("MAT_SCENE_Star", "#DCE8FF", 6.0)
MAT_BULB_WARM = emission_material("MAT_SCENE_BulbWarm", "#FFC070", 0.85)
MAT_BOAT_PAPER = principled("MAT_SCENE_BoatPaper", "#FFE0AE", roughness=0.55,
                            emission="#FFB15E", emission_strength=2.6)
MAT_BULB_RED = emission_material("MAT_SCENE_BulbRed", "#FF6A3A", 1.05)
MAT_BULB_GOLD = emission_material("MAT_SCENE_BulbGold", "#FFD98A", 0.72)
MAT_TOWER_GLOW = emission_material("MAT_SCENE_TowerGlow", "#FFC06A", 4.0)
MAT_FIREWORK_GOLD = emission_material("MAT_SCENE_FireworkGold", "#FFD27A", 22.0)
MAT_FIREWORK_ROSE = emission_material("MAT_SCENE_FireworkRose", "#FF6FA8", 22.0)
MAT_FIREWORK_CYAN = emission_material("MAT_SCENE_FireworkCyan", "#7BE8FF", 22.0)
MAT_BARK = principled("MAT_SCENE_Bark", "#3B2A22", roughness=0.86,
                     bump=0.10, bump_scale=5)
MAT_TRUNK = principled("MAT_SCENE_Trunk", "#2A1A18", roughness=0.7, bump=0.25, bump_scale=8)
MAT_PETAL = principled("MAT_SCENE_Petal", "#FFB7D4", roughness=0.5,
                       emission="#FF9CC4", emission_strength=0.25, alpha=0.9)
MAT_BOAT_WOOD = principled("MAT_SCENE_BoatWood", "#3B2620", roughness=0.45, coat=0.2)
MAT_BOAT_ROOF = principled("MAT_SCENE_BoatRoof", "#1E2B2E", roughness=0.4, coat=0.2)
MAT_SOFT_MIST = principled("MAT_SCENE_Mist", "#8FA6D8", roughness=1.0,
                           emission="#6F86B8", emission_strength=0.10, alpha=0.028)

# Tame the kit's authored emission for a night beauty shot; the exported kit
# materials keep their original values for runtime use.
for mat_name, strength in (("MAT_LR_Paper_Glow", 1.18), ("MAT_LR_Paper_Red", 1.25)):
    mat = bpy.data.materials.get(mat_name)
    if mat and mat.use_nodes:
        node = mat.node_tree.nodes.get("Principled BSDF")
        if node:
            node.inputs["Emission Strength"].default_value = strength
            if mat_name == "MAT_LR_Paper_Glow":
                node.inputs["Base Color"].default_value = (*srgb("#E8B070"), 1.0)
                node.inputs["Emission Color"].default_value = (*srgb("#FF8A3D"), 1.0)
            else:
                node.inputs["Emission Color"].default_value = (*srgb("#FF4D3D"), 1.0)

# Lift the roof values so the tile courses survive the night grade.
for mat_name, hex_base, rough in (("MAT_LR_Roof_Tile", "#46545B", 0.42),
                                  ("MAT_LR_Roof_Blue", "#465A58", 0.44)):
    mat = bpy.data.materials.get(mat_name)
    if mat and mat.use_nodes:
        node = mat.node_tree.nodes.get("Principled BSDF")
        if node:
            node.inputs["Base Color"].default_value = (*srgb(hex_base), 1.0)
            node.inputs["Roughness"].default_value = rough

# Shorthand for the kit materials reused by the street props.
MAT_LR_Wood_Dark = bpy.data.materials["MAT_LR_Wood_Dark"]
MAT_LR_Wood_Warm = bpy.data.materials["MAT_LR_Wood_Warm"]
MAT_LR_Stone_Light = bpy.data.materials["MAT_LR_Stone_Light"]
MAT_LR_Cloth_Cream = bpy.data.materials["MAT_LR_Cloth_Cream"]
MAT_LR_Paper_Glow = bpy.data.materials["MAT_LR_Paper_Glow"]
MAT_LR_Gold = bpy.data.materials["MAT_LR_Gold"]
MAT_LR_Lacquer_Red = bpy.data.materials["MAT_LR_Lacquer_Red"]
MAT_LR_Plaster_Warm = bpy.data.materials["MAT_LR_Plaster_Warm"]
MAT_LR_Plaster_Sand = bpy.data.materials["MAT_LR_Plaster_Sand"]
MAT_LR_Roof_Tile = bpy.data.materials["MAT_LR_Roof_Tile"]
MAT_LR_Roof_Blue = bpy.data.materials["MAT_LR_Roof_Blue"]

MAT_QUAY_LANTERN = principled("MAT_SCENE_QuayLantern", "#D96A38", roughness=0.55,
                              emission="#FF7A3A", emission_strength=0.38)
# Hillside and waterfront planting.  The far tree line is deliberately dark and
# desaturated so it reads as depth behind the lit shopfronts.
MAT_PINE = principled("MAT_SCENE_Pine", "#14261F", roughness=0.92, bump=0.2, bump_scale=5)
MAT_WILLOW = principled("MAT_SCENE_Willow", "#3D5A32", roughness=0.86, bump=0.15, bump_scale=7)
MAT_REED = principled("MAT_SCENE_Reed", "#55502E", roughness=0.88)
MAT_LOTUS_LEAF = principled("MAT_SCENE_LotusLeaf", "#22402C", roughness=0.68, coat=0.25)
MAT_LOTUS_FLOWER = principled("MAT_SCENE_LotusFlower", "#C26880", roughness=0.6,
                              emission="#4A1424", emission_strength=0.35)
MAT_SKIN = principled("MAT_SCENE_Skin", "#B98A6A", roughness=0.72)
MAT_INDIGO = principled("MAT_SCENE_Indigo", "#18203A", roughness=0.85)
MAT_PLUM = principled("MAT_SCENE_Plum", "#38202E", roughness=0.85)
MAT_CREAM = principled("MAT_SCENE_Cream", "#D8C39A", roughness=0.82)
MAT_BANNER = principled("MAT_SCENE_Banner", "#8C2430", roughness=0.78,
                        emission="#3A0A10", emission_strength=0.25)

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def move_to_collection(obj, col):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    col.objects.link(obj)


def add_box(name, size, location, material, collection, rotation=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if bevel > 0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 1
        mod.limit_method = "ANGLE"
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_cylinder(name, vertices, radius, depth, location, material, collection,
                 rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                        end_fill_type="TRIFAN", location=location,
                                        rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_sphere(name, radius, location, material, collection, segments=12, rings=6,
               scale=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings,
                                         radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    if scale:
        obj.scale = scale
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def add_cone(name, vertices, radius1, radius2, depth, location, material, collection,
             rotation=(0, 0, 0), scale=None):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1,
                                    radius2=radius2, depth=depth,
                                    end_fill_type="TRIFAN", location=location,
                                    rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if scale:
        obj.scale = scale
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
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
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def make_card_object(name, cards, material, collection):
    """Build one mesh from many quads, each sampling one tile of the atlas.

    `cards` holds (centre, size, rotation, tile, spin, flip).  A small UV inset
    keeps mipmaps from bleeding the neighbouring tile into the card.
    """
    verts = []
    faces = []
    uvs = []
    inset = 0.006
    span = 0.5 - inset * 2.0
    corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    quad_uv = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))

    for centre, size, rotation, tile, spin, flip in cards:
        base = len(verts)
        for cx, cz in corners:
            local = Vector((cx * size * 0.5, 0.0, cz * size * 0.5))
            verts.append(tuple(centre + rotation @ local))
        faces.append((base, base + 1, base + 2, base + 3))

        u0 = (tile % 2) * 0.5 + inset
        v0 = (tile // 2) * 0.5 + inset
        order = list(quad_uv[spin:] + quad_uv[:spin])
        if flip:
            order = order[::-1]
        for lu, lv in order:
            uvs.append((u0 + lu * span, v0 + lv * span))

    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name="UVMap")
    for index, uv in enumerate(uvs):
        layer.data[index].uv = uv
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def _card_rotation(rng, upright=False, facing=0.0):
    if upright:
        return Matrix.Rotation(facing + rng.uniform(-0.6, 0.6), 3, "Z")
    return (Matrix.Rotation(rng.uniform(0, math.tau), 3, "Z")
            @ Matrix.Rotation(rng.uniform(0, math.tau), 3, "Y")
            @ Matrix.Rotation(rng.uniform(0, math.tau), 3, "X"))


def build_shrub(name, centre, size=0.9, count=9, seed=0, collection=None):
    """A leafy clump built from cards; replaces the old ball-shaped plant."""
    rng = random.Random(seed)
    cards = []
    for _ in range(count):
        offset = Vector((rng.uniform(-0.20, 0.20), rng.uniform(-0.20, 0.20),
                         rng.uniform(-0.14, 0.20))) * (size / 0.9)
        cards.append((Vector(centre) + offset, size * rng.uniform(0.85, 1.15),
                      _card_rotation(rng), rng.randrange(4), rng.randrange(4),
                      rng.random() < 0.5))
    make_card_object(name, cards, MAT_SHRUB_CARD, collection)


def add_curve_tube(name, points, radius, material, collection, resolution_u=2,
                   bevel_resolution=1):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution_u
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    curve.bevel_depth = radius
    curve.bevel_resolution = bevel_resolution
    curve.use_fill_caps = True
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def new_from_mesh(name, mesh, material, location, rotation_z=0.0, scale=1.0,
                  collection=COL_PROPS):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (0, 0, rotation_z)
    obj.scale = (scale, scale, scale)
    if material is not None:
        if mesh.materials:
            mesh.materials[0] = material
        else:
            mesh.materials.append(material)
    return obj


def instance_kit(src_name, new_name, location, rot_z=0.0, scale=1.0,
                 collection=COL_BUILDINGS, scale_z=None, scale_x=None):
    src = bpy.data.objects[src_name]
    obj = bpy.data.objects.new(new_name, src.data)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (0, 0, rot_z)
    sx = scale if scale_x is None else scale_x
    sz = scale if scale_z is None else scale_z
    obj.scale = (sx, scale, sz)
    return obj


def append_object(blend_path, object_name, collection):
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        data_to.objects = [object_name]
    obj = data_to.objects[0]
    collection.objects.link(obj)
    return obj


def add_camera(name, location, target, lens):
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = lens
    cam_data.sensor_width = 36.0
    cam_data.clip_start = 0.2
    cam_data.clip_end = 3000.0
    cam = bpy.data.objects.new(name, cam_data)
    COL_CAMERAS.objects.link(cam)
    cam.location = location
    direction = Vector(target) - Vector(location)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


def add_point_light(name, location, color_hex, power, radius, shadow=False):
    data = bpy.data.lights.new(name, "POINT")
    data.energy = power
    data.color = srgb(color_hex)
    data.shadow_soft_size = radius
    data.use_shadow = shadow
    obj = bpy.data.objects.new(name, data)
    COL_LIGHTS.objects.link(obj)
    obj.location = location
    return obj


def add_area_light(name, location, target, color_hex, power, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.color = srgb(color_hex)
    data.shape = "DISK"
    data.size = size
    data.use_shadow = False
    obj = bpy.data.objects.new(name, data)
    COL_LIGHTS.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
    return obj

# ---------------------------------------------------------------------------
# Sky, stars, mountains
# ---------------------------------------------------------------------------

def build_sky():
    mat = bpy.data.materials.new("MAT_SCENE_SkyGradient")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "EASE"
    stops = [
        (0.00, "#02040C"),
        (0.44, "#040A1E"),
        (0.485, "#0B1640"),
        (0.505, "#2B4A9A"),
        (0.525, "#6A5F9A"),
        (0.55, "#2A2050"),
        (0.66, "#0B1640"),
        (0.82, "#050B26"),
        (1.00, "#03071A"),
    ]
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    first = ramp.color_ramp.elements[0]
    first.position = stops[0][0]
    first.color = (*srgb(stops[0][1]), 1)
    for pos, hex_color in stops[1:]:
        el = ramp.color_ramp.elements.new(pos)
        el.color = (*srgb(hex_color), 1)
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])

    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1600,
                                         location=(0, 0, 0))
    sky = bpy.context.object
    sky.name = "ENV_SkyDome"
    sky.data.materials.append(mat)
    move_to_collection(sky, COL_SKY)
    for poly in sky.data.polygons:
        poly.use_smooth = True
    sky.hide_select = True

    # Stars: quads tangent to the dome, one mesh.
    verts = []
    faces = []
    star_rng = random.Random(SEED + 1)
    for _ in range(1500):
        theta = star_rng.uniform(0, math.tau)
        z = star_rng.uniform(0.03, 0.98)
        rxy = math.sqrt(max(0.0, 1.0 - z * z))
        direction = Vector((rxy * math.cos(theta), rxy * math.sin(theta), z))
        pos = direction * 1500.0
        side = Vector((-math.sin(theta), math.cos(theta), 0.0))
        up = direction.cross(side).normalized()
        size = star_rng.uniform(0.55, 2.4)
        if star_rng.random() < 0.06:
            size *= 1.7
        p = pos
        base = len(verts)
        verts.extend([
            tuple(p - side * size - up * size),
            tuple(p + side * size - up * size),
            tuple(p + side * size + up * size),
            tuple(p - side * size + up * size),
        ])
        faces.append((base, base + 1, base + 2, base + 3))
    stars = add_mesh_object("ENV_Stars", verts, faces, MAT_STAR, COL_SKY)
    stars.visible_shadow = False


def mountain_ring(name, radius, base_z, h_min, h_max, material, offset=0.0,
                  segments=160):
    rng = random.Random(SEED + int(radius))
    verts = []
    faces = []
    for i in range(segments):
        angle = math.tau * i / segments
        h = h_min + (h_max - h_min) * (0.5 + 0.5 * math.sin(angle * 3.0 + offset))
        h += rng.uniform(-0.22, 0.22) * (h_max - h_min)
        h = max(h_min * 0.6, h)
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        verts.append((x, y, base_z - 8.0))
        verts.append((x, y, base_z + h))
    for i in range(segments):
        a = i * 2
        b = ((i + 1) % segments) * 2
        faces.append((a, b, b + 1, a + 1))
    obj = add_mesh_object(name, verts, faces, material, COL_ENV)
    return obj

# ---------------------------------------------------------------------------
# Ground, water, quays
# ---------------------------------------------------------------------------

# A canal, not a harbour.  The reference render reads as a narrow water street
# with room to walk both banks, so the channel is 25 m across and the paved
# promenade in front of the shopfronts is 7.5 m wide.
RIVER_HALF = 12.5
PROMENADE = 7.5
GROUND_Z = 1.2
BRIDGE_Y = 10.0
TOWER_Y = 78.0
PAVILION_Y = 62.0
# The kit bridge spans 47.3 m.  Compress X so it lands on the promenade instead
# of the shop wall; the deck profile and its height stay as authored.
BRIDGE_HALF = 17.5
BRIDGE_KIT_HALF = 23.63

build_sky()
mountain_ring("ENV_Mountains_Far", 900, 0, 30, 62, MAT_MOUNTAIN_FAR, offset=0.4)
mountain_ring("ENV_Mountains_Near", 620, 0, 16, 38, MAT_MOUNTAIN_NEAR, offset=2.1)

# River water.
water = add_box("ENV_Water", (RIVER_HALF * 2.0, 380.0, 0.04),
                (0, 20, 0.02), MAT_WATER, COL_ENV)

# Dark underlay so no sky leaks through gaps.
underlay = add_box("ENV_Underlay", (1800, 1800, 0.2), (0, 0, -0.65),
                   principled("MAT_SCENE_Underlay", "#050814", roughness=1.0), COL_ENV)
underlay.visible_shadow = False

# Bank ground slabs and quay walls.
for side in (-1, 1):
    ground = add_box(f"ENV_Ground_{side}", (78, 380, 0.40),
                     (side * (RIVER_HALF + 39.0), 20, GROUND_Z - 0.20),
                     MAT_PAVING, COL_BANKS)
    ground.visible_shadow = True
    # Quay wall face and coping stone.
    add_box(f"ENV_QuayWall_{side}", (1.5, 380, 1.25),
            (side * (RIVER_HALF + 0.75), 20, 0.625), MAT_QUAY, COL_BANKS)
    add_box(f"ENV_QuayCoping_{side}", (1.95, 380, 0.16),
            (side * (RIVER_HALF + 0.80), 20, 1.24),
            bpy.data.materials["MAT_LR_Stone_Light"], COL_BANKS)
    # A darker mooring band at the waterline.
    add_box(f"ENV_Waterline_{side}", (0.12, 380, 0.34),
            (side * (RIVER_HALF + 0.02), 20, 0.17),
            principled(f"MAT_SCENE_Algae_{side}", "#1B2A2A", roughness=0.9), COL_BANKS)

# Steps into the water at two ferry points on the right bank.
for y in (-48.0, 118.0):
    for i in range(5):
        add_box(f"ENV_WaterStep_{y}_{i}", (2.3 - i * 0.14, 3.4, 0.22),
                (RIVER_HALF - 0.2 + i * 0.26, y, 0.10 + i * 0.22),
                MAT_QUAY, COL_BANKS)

# Bridge abutments.
for side in (-1, 1):
    add_box(f"ENV_BridgeAbutment_{side}", (4.0, 9.0, 1.4),
            (side * BRIDGE_HALF, BRIDGE_Y, 0.7), MAT_QUAY, COL_BANKS)

# ---------------------------------------------------------------------------
# Authored asset sources (Shangyuan shops and stalls)
# ---------------------------------------------------------------------------

COL_SOURCES = new_collection("COL_Sources", COL_ROOT)
SHANGYUAN_MODELS = os.path.join(os.path.dirname(ASSET_DIR), "shangyuan", "models")


def unify_materials(objects):
    """Share one datablock per authored material name across imports.

    Every GLB carries its own copy of the SY_* materials.  Left alone, six shop
    imports would become six identically named sets and six copies of every
    texture in the export; remapping to the first copy keeps one set.
    """
    for obj in objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                continue
            base = material.name.split(".")[0]
            existing = bpy.data.materials.get(base)
            if existing is not None and existing is not material:
                slot.material = existing
                bpy.data.materials.remove(material, do_unlink=True)


def import_source(filename, name):
    """Import one authored GLB and join it into a hidden, centred mesh source.

    The source is kept out of the exported collections and reused through
    `instance_kit`, the same way the kit masters are.
    """
    path = os.path.join(SHANGYUAN_MODELS, filename)
    if not os.path.exists(path):
        print("LR_MISSING_SOURCE", path)
        return None
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    if not meshes:
        return None
    # Signs are parented to the body; bake the parent transform so the join and
    # every later instance share one clean origin.
    for obj in meshes:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
        move_to_collection(obj, COL_SOURCES)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    source = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    unify_materials([source])
    # Centre the footprint on the origin and drop the base to z = 0 so a
    # placement is just (x, y, ground) for every source.
    low = Vector((min(c[i] for c in source.bound_box) for i in range(3)))
    high = Vector((max(c[i] for c in source.bound_box) for i in range(3)))
    offset = Vector((-(low.x + high.x) / 2, -(low.y + high.y) / 2, -low.z))
    for vertex in source.data.vertices:
        vertex.co += offset
    source.data.update()
    source.name = name
    source.data.name = name
    source.hide_render = True
    source.hide_set(True)
    return source


SHOP_SOURCES = [
    "model-shop-01", "model-shop-02", "model-shop-03",
    "model-shop-04", "model-shop-05", "model-shop-06",
]
for index, filename in enumerate(SHOP_SOURCES):
    import_source(filename + ".glb", f"SRC_Shop_{index + 1:02d}")
import_source("model-stall-riddle.glb", "SRC_Stall_Riddle")
import_source("model-stall-tea.glb", "SRC_Stall_Tea")
# Reuse the remaining authored waterfront pieces instead of building new ones:
# the performance stage is the visible source of the 打铁花 show, the ferry dock
# gives the water steps a real landing, and the skiff/boat add river traffic.
for filename, source_name in (
    ("model-performance.glb", "SRC_Performance"),
    ("model-quay.glb", "SRC_FerryDock"),
    ("model-skiff.glb", "SRC_Skiff"),
    ("model-boat.glb", "SRC_Boat"),
):
    import_source(filename, source_name)

# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------

def footprint_dims(name):
    src = bpy.data.objects[name]
    return src.dimensions.x, src.dimensions.y


def place_row(side, y_start, y_end, gap_zones, prefix):
    """Fill one bank with linked shophouses, facade on the river line.

    The kit's three variants are mixed with the six authored Shangyuan
    shopfronts so the street has nine rooflines, signboards and storey
    combinations instead of three repeating bays.
    """
    variants = [
        ("SM_Env_Shophouse_A_01", 0.14),
        ("SM_Env_Shophouse_B_01", 0.10),
        ("SM_Env_Shophouse_C_01", 0.12),
        ("SRC_Shop_01", 0.10),
        ("SRC_Shop_02", 0.12),
        ("SRC_Shop_03", 0.08),
        ("SRC_Shop_04", 0.11),
        ("SRC_Shop_05", 0.09),
        ("SRC_Shop_06", 0.14),
    ]
    variants = [(name, weight) for name, weight in variants if bpy.data.objects.get(name)]
    names = [name for name, _ in variants]
    weights = [weight for _, weight in variants]
    rng = random.Random(SEED + (11 if side > 0 else 29))
    y = y_start
    idx = 0
    while y < y_end:
        name = rng.choices(names, weights=weights)[0]
        width, depth = footprint_dims(name)
        center_y = y + width / 2.0
        if center_y + width / 2.0 > y_end:
            break
        skip = any(g0 - width / 2 < center_y < g1 + width / 2 for g0, g1 in gap_zones)
        if skip:
            y += 2.4
            continue
        rot = -math.pi / 2 if side > 0 else math.pi / 2
        # The promenade is part of the level: the shopfronts sit PROMENADE
        # metres back from the water so there is a walkable street.
        facade_x = side * (RIVER_HALF + PROMENADE)
        center_x = facade_x + side * depth / 2.0
        z_scale = rng.uniform(0.94, 1.10)
        instance_kit(name, f"{prefix}_{idx:02d}", (center_x, center_y, GROUND_Z),
                     rot_z=rot, scale=1.0, scale_z=z_scale)
        idx += 1
        y += width + rng.uniform(0.3, 1.3)
    return idx


place_row(1, -140.0, 180.0, [(-2.0, 22.0), (28.0, 84.0)], "BLD_R")
place_row(-1, -140.0, 180.0, [(-2.0, 22.0)], "BLD_L")

# The bridge landing leaves a wide hole in both rows.  Two shophouses per bank
# frame the bridgehead and bring the street back down to the water.
for side, sources in (
    (1, (("SRC_Shop_03", 0.0), ("SRC_Shop_01", 19.2))),
    (-1, (("SRC_Shop_01", 0.0), ("SRC_Shop_03", 19.2))),
):
    for index, (source, y) in enumerate(sources):
        if bpy.data.objects.get(source) is None:
            continue
        _, depth = footprint_dims(source)
        facade_x = side * (RIVER_HALF + PROMENADE)
        instance_kit(source, f"BLD_{'R' if side > 0 else 'L'}_Bridge_{index}",
                     (facade_x + side * depth / 2.0, y, GROUND_Z),
                     rot_z=-math.pi / 2 if side > 0 else math.pi / 2,
                     scale_z=1.04, collection=COL_BUILDINGS)

# ---------------------------------------------------------------------------
# Pavilion square: a grand restaurant closes the south side and a three-house
# terrace walls the east side, so the square reads as a real market courtyard
# instead of a gap in the shop row.
# ---------------------------------------------------------------------------

# Two-storey restaurant set back from the shop line, leaving a forecourt for
# its lanterns and a side lane into the square.
PLAZA_SOUTH_X = 31.0
PLAZA_SOUTH_Y = 39.0
restaurant = instance_kit("SRC_Shop_06", "BLD_R_Restaurant_00",
                          (PLAZA_SOUTH_X, PLAZA_SOUTH_Y, GROUND_Z),
                          rot_z=-math.pi / 2, collection=COL_BUILDINGS)
restaurant.scale = (1.0, 1.08, 1.08)

# Terrace along the back of the square, facing the pavilion across the stone.
PLAZA_BACK_X = 38.5
for index, (source, y, z_scale) in enumerate((
    ("SRC_Shop_01", 52.6, 1.02),
    ("SRC_Shop_02", 64.4, 1.06),
    ("SRC_Shop_06", 79.2, 0.98),
)):
    if bpy.data.objects.get(source) is None:
        continue
    _, depth = footprint_dims(source)
    instance_kit(source, f"BLD_R_PlazaBack_{index:02d}",
                 (PLAZA_BACK_X + depth / 2.0, y, GROUND_Z),
                 rot_z=-math.pi / 2, scale_z=z_scale, collection=COL_BUILDINGS)

# ---------------------------------------------------------------------------
# Skyline: two rows of roofs behind the shopfronts.  A single row of buildings
# makes the town end at the first roofline; these blocks layer the skyline and
# carry a few lit windows without paying for full facades the player never sees.
# ---------------------------------------------------------------------------

def build_roof_block(name, center_x, center_y, width, depth, body_h, roof_h,
                     wall_mat, roof_mat, lit=3, detail=True):
    z0 = GROUND_Z
    add_box(f"{name}_Body", (width, depth, body_h),
            (center_x, center_y, z0 + body_h / 2.0), wall_mat, COL_BUILDINGS)
    # Gable roof with a ridge along the street; the river-facing slope catches
    # the skyline light.
    over = 0.7
    half_w = width / 2.0 + over
    half_d = depth / 2.0 + over
    ridge = width * 0.16
    verts = [
        (center_x - half_w, center_y - half_d, z0 + body_h),
        (center_x + half_w, center_y - half_d, z0 + body_h),
        (center_x + half_w, center_y + half_d, z0 + body_h),
        (center_x - half_w, center_y + half_d, z0 + body_h),
        (center_x - ridge, center_y, z0 + body_h + roof_h),
        (center_x + ridge, center_y, z0 + body_h + roof_h),
    ]
    faces = [
        (0, 1, 5, 4),
        (2, 3, 4, 5),
        (1, 2, 5),
        (3, 0, 4),
    ]
    add_mesh_object(f"{name}_Roof", verts, faces, roof_mat, COL_BUILDINGS)
    river_sign = -1.0 if center_x > 0 else 1.0
    if not detail:
        # Far skyline row: a plinth, a timber belt and one lit window band keep
        # the distant blocks reading as houses instead of pale slabs.
        add_box(f"{name}_Plinth", (width + 0.2, depth + 0.2, 0.6),
                (center_x, center_y, z0 + 0.3), MAT_QUAY, COL_BUILDINGS)
        add_box(f"{name}_Belt", (0.12, depth + 0.12, 0.14),
                (center_x + river_sign * (width / 2.0 + 0.05), center_y,
                 z0 + body_h * 0.66), MAT_LR_Wood_Dark, COL_BUILDINGS)
        for i in range(3):
            wy = center_y + (i - 1) * depth * 0.28
            wx = center_x + river_sign * (width / 2.0 + 0.02)
            add_box(f"{name}_WinFrame_{i}", (0.05, 0.62, 0.94),
                    (wx, wy, z0 + body_h * 0.58),
                    MAT_LR_Wood_Dark, COL_BUILDINGS)
            add_box(f"{name}_Win_{i}", (0.06, 0.50, 0.80),
                    (wx + river_sign * 0.025, wy, z0 + body_h * 0.58),
                    MAT_LR_Paper_Glow, COL_BUILDINGS)
        # The gable ends are what a diagonal view sees; two small panes keep
        # them from reading as blank plaster.
        for sy in (-1, 1):
            for i in range(2):
                wx = center_x + (i - 0.5) * width * 0.34
                wy = center_y + sy * (depth / 2.0 + 0.02)
                add_box(f"{name}_SideFrame_{sy}_{i}", (0.62, 0.05, 0.84),
                        (wx, wy, z0 + body_h * 0.52),
                        MAT_LR_Wood_Dark, COL_BUILDINGS)
                add_box(f"{name}_SideWin_{sy}_{i}", (0.50, 0.06, 0.72),
                        (wx, wy + sy * 0.02, z0 + body_h * 0.52),
                        MAT_LR_Paper_Glow, COL_BUILDINGS)
        return
    # A stone plinth and two timber belts wrap all four walls, so a block seen
    # through a gap reads as a timber-framed house instead of a pale slab.
    add_box(f"{name}_Plinth", (width + 0.22, depth + 0.22, 0.55),
            (center_x, center_y, z0 + 0.275), MAT_QUAY, COL_BUILDINGS)
    for level, hh in ((0.46, 0.10), (0.80, 0.12)):
        bz = z0 + body_h * level
        add_box(f"{name}_BeltY_{level}", (0.10, depth + 0.10, hh),
                (center_x - width / 2.0 - 0.04, center_y, bz),
                MAT_LR_Wood_Dark, COL_BUILDINGS)
        add_box(f"{name}_BeltY2_{level}", (0.10, depth + 0.10, hh),
                (center_x + width / 2.0 + 0.04, center_y, bz),
                MAT_LR_Wood_Dark, COL_BUILDINGS)
        add_box(f"{name}_BeltX_{level}", (width + 0.10, 0.10, hh),
                (center_x, center_y - depth / 2.0 - 0.04, bz),
                MAT_LR_Wood_Dark, COL_BUILDINGS)
        add_box(f"{name}_BeltX2_{level}", (width + 0.10, 0.10, hh),
                (center_x, center_y + depth / 2.0 + 0.04, bz),
                MAT_LR_Wood_Dark, COL_BUILDINGS)
    for sx in (-1, 1):
        for sy in (-1, 1):
            add_box(f"{name}_Corner_{sx}_{sy}", (0.18, 0.18, body_h),
                    (center_x + sx * (width / 2.0 + 0.02),
                     center_y + sy * (depth / 2.0 + 0.02),
                     z0 + body_h / 2.0), MAT_LR_Wood_Dark, COL_BUILDINGS)
    # Two rows of shoji on the river wall, sized to the wall rather than the
    # block's street frontage so the outer panes stay on the facade.
    per_row = max(2, min(4, lit))
    for r, rz in enumerate((0.34, 0.66)):
        for i in range(per_row):
            wy = center_y + (i - (per_row - 1) / 2.0) * (depth / per_row) * 0.70
            wz = z0 + body_h * rz
            wx = center_x + river_sign * (width / 2.0 + 0.02)
            add_box(f"{name}_WinFrame_{r}_{i}", (0.05, 0.66, 1.04),
                    (wx, wy, wz), MAT_LR_Wood_Dark, COL_BUILDINGS)
            add_box(f"{name}_Win_{r}_{i}", (0.06, 0.52, 0.86),
                    (wx + river_sign * 0.025, wy, wz),
                    MAT_LR_Paper_Glow, COL_BUILDINGS)
    # Side-wall panes keep the gaps between shops from reading as blank walls.
    for s, sy in ((0, -1), (1, 1)):
        for r, rz in enumerate((0.40, 0.70)):
            wy = center_y + sy * (depth / 2.0 + 0.02)
            wx = center_x + (r - 0.5) * width * 0.34
            wz = z0 + body_h * rz
            add_box(f"{name}_SideWin_{s}_{r}", (0.62, 0.06, 0.82),
                    (wx, wy, wz), MAT_LR_Paper_Glow, COL_BUILDINGS)
    # A small tiled eave over the lower windows.
    add_box(f"{name}_Eave", (0.60, depth + 0.55, 0.10),
            (center_x + river_sign * (width / 2.0 + 0.24), center_y,
             z0 + body_h * 0.52), roof_mat, COL_BUILDINGS)


back_rng = random.Random(SEED + 303)
for side in (-1, 1):
    y = -138.0
    index = 0
    while y < 172.0:
        width = back_rng.uniform(9.0, 16.0)
        depth = back_rng.uniform(8.0, 13.0)
        # Keep the pavilion square open on the east bank.
        if side > 0 and y + width > 24.0 and y < 90.0:
            y += 8.0
            continue
        build_roof_block(
            f"BLD_RoofBack_{'R' if side > 0 else 'L'}_{index:02d}",
            side * 37.0, y + width / 2.0, width, depth,
            back_rng.uniform(6.6, 10.2), back_rng.uniform(2.0, 3.4),
            back_rng.choice((MAT_LR_Plaster_Warm, MAT_LR_Plaster_Sand, MAT_CREAM)),
            back_rng.choice((MAT_LR_Roof_Tile, MAT_LR_Roof_Blue)),
            lit=back_rng.randint(2, 4),
        )
        index += 1
        y += width + back_rng.uniform(2.0, 5.0)

# A farther, taller row closes the horizon behind the near roofs.
for side in (-1, 1):
    y = -132.0
    index = 0
    while y < 168.0:
        width = back_rng.uniform(13.0, 20.0)
        depth = back_rng.uniform(10.0, 16.0)
        build_roof_block(
            f"BLD_RoofFar_{'R' if side > 0 else 'L'}_{index:02d}",
            side * 55.0, y + width / 2.0, width, depth,
            back_rng.uniform(8.6, 12.4), back_rng.uniform(2.6, 4.2),
            back_rng.choice((MAT_LR_Plaster_Sand, MAT_LR_Plaster_Warm,
                             MAT_LR_Plaster_Warm)),
            back_rng.choice((MAT_LR_Roof_Tile, MAT_LR_Roof_Blue)),
            lit=back_rng.randint(1, 3), detail=False,
        )
        index += 1
        y += width + back_rng.uniform(4.0, 8.0)

# Two smaller lantern towers on the hillside give the eye a third landmark
# beyond the bridge and the main tower.
for i, (x, y, s) in enumerate(((-72.0, 42.0, 0.9), (68.0, 150.0, 0.82))):
    instance_kit("SM_Env_LanternTower_01", f"LM_DistantTower_{i}",
                 (x, y, 0.0), scale=s, collection=COL_LANDMARKS)

# Bridge.
bridge = instance_kit("SM_Env_Bridge_Arch_01", "LM_Bridge_Arch", (0, BRIDGE_Y, 0.0),
                      scale_x=BRIDGE_HALF / BRIDGE_KIT_HALF, collection=COL_LANDMARKS)

# Lantern tower on its stone island, scaled up as the visual anchor.
tower = instance_kit("SM_Env_LanternTower_01", "LM_Lantern_Tower", (0, TOWER_Y, 0.0),
                     scale=1.25, collection=COL_LANDMARKS)

# Existing pavilion on the right-bank plaza, facing the river.
pavilion = append_object(PAVILION_BLEND, "SM_Env_Pavilion_Hex_01", COL_LANDMARKS)
pavilion.name = "LM_Pavilion_Hex"
pavilion.location = (30.5, PAVILION_Y, GROUND_Z)
pavilion.rotation_euler = (0, 0, -math.pi / 2)
pavilion.scale = (1.45, 1.45, 1.45)

# Stone plaza in front of the pavilion, opening off the promenade.
add_box("ENV_PavilionPlaza", (18.0, 28.0, 0.10),
        (29.5, PAVILION_Y, GROUND_Z + 0.05),
        bpy.data.materials["MAT_LR_Stone_Light"], COL_BANKS)
for i in range(3):
    add_box(f"ENV_PlazaStep_{i}", (0.65, 20.0 - i * 1.4, 0.09),
            (RIVER_HALF + PROMENADE + 0.2 + i * 0.65, PAVILION_Y,
             GROUND_Z - 0.02 - i * 0.09),
            MAT_QUAY, COL_BANKS)

# Ceremonial gate at the street entrance, reusing the original Shangyuan asset.
# It is centred on the promenade; its width is compressed while its height keeps
# a 2.2 m clearance, so it frames the street without becoming a barrier.
PAIFANG_SOURCE = os.path.join(os.path.dirname(ASSET_DIR), "shangyuan", "models",
                              "model-paifang.glb")
PAIFANG_SCALE = 0.36
PAIFANG_HEIGHT = 0.8
PAIFANG_X = RIVER_HALF + PROMENADE * 0.5
if os.path.exists(PAIFANG_SOURCE):
    bpy.ops.import_scene.gltf(filepath=PAIFANG_SOURCE)
    imported = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    for obj in imported:
        move_to_collection(obj, COL_LANDMARKS)
    # The gate carries its own copy of the SY_* materials; share the set the
    # shops already imported so the export keeps one texture per material.
    unify_materials(imported)
    # The sign is parented to the gate; transform only the root so it is not
    # moved twice by the inherited parent matrix.
    roots = [obj for obj in imported if obj.parent is None or obj.parent not in imported]
    transform = (
        Matrix.Translation((PAIFANG_X, -120.0, GROUND_Z))
        @ Matrix.Rotation(math.pi / 2, 4, "Z")
        @ Matrix.Diagonal(Vector((PAIFANG_SCALE, PAIFANG_SCALE, PAIFANG_HEIGHT, 1.0)))
    )
    for obj in roots:
        obj.matrix_world = transform @ obj.matrix_world
    for obj in imported:
        if obj.name.startswith("model-paifang"):
            obj.name = "LM_Paifang"
        elif "Sign" in obj.name:
            obj.name = "LM_Paifang_Sign"
        for slot in obj.material_slots:
            material = slot.material
            if material is None or material.name != "SY_Lantern" or not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    node.inputs["Emission Strength"].default_value = 1.5
else:
    print("LR_MISSING_PAIFANG", PAIFANG_SOURCE)

# Palace lanterns hang from their top ring, so each pair needs a timber stand;
# placed on the ground their bodies would sink under the paving.
for i, y in enumerate((PAVILION_Y - 4.6, PAVILION_Y + 4.6)):
    add_cylinder(f"PROP_PalaceLantern_{i}_Post", 8, 0.07, 3.9,
                 (25.7, y, GROUND_Z + 1.95),
                 bpy.data.materials["MAT_LR_Wood_Dark"], COL_PROPS)
    add_box(f"PROP_LanternArm_Pavilion_{i}", (0.95, 0.09, 0.09),
            (26.15, y, GROUND_Z + 3.86),
            bpy.data.materials["MAT_LR_Wood_Dark"], COL_PROPS)
    lantern = append_object(LANTERN_BLEND, "SM_PalaceLantern_6S", COL_PROPS)
    lantern.name = f"PROP_PalaceLantern_{i}"
    lantern.location = (26.6, y, GROUND_Z + 3.8)
    lantern.scale = (1.35, 1.35, 1.35)
    add_point_light(f"LGT_PalaceLantern_{i}", (26.6, y, GROUND_Z + 2.5),
                    "#FFB066", 60.0, 0.4)

# The restaurant entrance repeats the same lantern through the shared mesh, so
# the export keeps one material set for all four.
for i, y in enumerate((35.6, 42.4)):
    add_cylinder(f"PROP_RestaurantLantern_{i}_Post", 8, 0.065, 3.5,
                 (21.2, y, GROUND_Z + 1.75),
                 bpy.data.materials["MAT_LR_Wood_Dark"], COL_PROPS)
    add_box(f"PROP_LanternArm_Restaurant_{i}", (0.9, 0.08, 0.08),
            (21.65, y, GROUND_Z + 3.46),
            bpy.data.materials["MAT_LR_Wood_Dark"], COL_PROPS)
    instance_kit("PROP_PalaceLantern_0", f"PROP_RestaurantLantern_{i}",
                 (22.1, y, GROUND_Z + 3.4), collection=COL_PROPS, scale=1.2)
    add_point_light(f"LGT_RestaurantLantern_{i}", (22.1, y, GROUND_Z + 2.25),
                    "#FFB066", 45.0, 0.4)

# Market stalls.  The interactive ones reuse the authored Shangyuan stall
# models — the riddle stall carries hanging riddle slips and a board, the tea
# stall a stove, cups and jars — instead of the kit's generic four-post awning.
# Each backs onto the shopfronts so the promenade keeps a clear walking lane.
STALL_SOURCES = {
    "riddle": "SRC_Stall_Riddle",
    "tea": "SRC_Stall_Tea",
}
# The two authored stalls alternate along both banks.  Their lanterns, signs,
# goods and counters are lit geometry, so every stall reads at night instead of
# turning into a dark box.
stall_specs = [
    (1, 40.0, "riddle"), (1, 118.0, "tea"), (-1, 34.0, "tea"),
    (1, -86.0, "riddle"), (1, -18.0, "tea"), (-1, -70.0, "riddle"),
    (-1, 150.0, "tea"), (1, 96.0, "riddle"), (1, 148.0, "tea"),
    (1, -40.0, "riddle"), (1, -66.0, "tea"), (1, 128.0, "riddle"),
    (-1, 62.0, "tea"), (-1, 100.0, "tea"), (-1, -30.0, "riddle"),
    (-1, -112.0, "tea"), (-1, -130.0, "riddle"), (-1, -96.0, "tea"),
    (-1, 132.0, "riddle"),
    # Market clusters: three more stalls on each approach plus one by the
    # bridgehead, so the street reads as a working market rather than a set.
    (1, 30.0, "tea"), (1, 48.0, "riddle"), (1, -118.0, "tea"),
    (1, -104.0, "riddle"), (-1, -78.0, "tea"), (-1, -50.0, "riddle"),
    (-1, 48.0, "tea"), (-1, 84.0, "riddle"),
]
for i, (side, y, kind) in enumerate(stall_specs):
    source = STALL_SOURCES[kind]
    if bpy.data.objects.get(source) is None:
        continue
    rot = -math.pi / 2 if side > 0 else math.pi / 2
    _, depth = footprint_dims(source)
    facade_x = side * (RIVER_HALF + PROMENADE)
    center_x = facade_x - side * (depth / 2.0 + 0.15)
    instance_kit(source, f"PROP_Stall_{i}", (center_x, y, GROUND_Z),
                 rot_z=rot, collection=COL_PROPS)

# Two tea stalls flank the approach to the pavilion, keeping its axis open.
for i, (kind, y) in enumerate((("tea", 56.5), ("tea", 72.0))):
    source = STALL_SOURCES[kind]
    if bpy.data.objects.get(source) is None:
        continue
    instance_kit(source, f"PROP_Stall_Plaza_{i}", (23.0, y, GROUND_Z),
                 rot_z=math.pi / 2, collection=COL_PROPS)

# ---------------------------------------------------------------------------
# Street dressing: goods, benches, banners and a few figures.  These are the
# near-field details that make the promenade feel lived in at eye height.
# ---------------------------------------------------------------------------

def add_barrel(name, x, y, z, scale=1.0):
    add_cylinder(name + "_Body", 10, 0.30 * scale, 0.68 * scale,
                 (x, y, z + 0.34 * scale), MAT_LR_Wood_Warm, COL_PROPS)
    for i, dz in enumerate((0.08, 0.60)):
        add_cylinder(f"{name}_Band_{i}", 10, 0.315 * scale, 0.05 * scale,
                     (x, y, z + dz * scale), MAT_LR_Wood_Dark, COL_PROPS)


def add_crate(name, x, y, z, size=0.68, rot=0.0):
    add_box(name + "_Box", (size, size * 0.9, size * 0.78),
            (x, y, z + size * 0.39), MAT_LR_Wood_Warm, COL_PROPS,
            rotation=(0, 0, rot))
    for i, dy in enumerate((-0.22, 0.22)):
        add_box(f"{name}_Slat_{i}", (size * 1.02, 0.06, size * 0.10),
                (x, y + dy * size, z + size * 0.72), MAT_LR_Wood_Dark,
                COL_PROPS, rotation=(0, 0, rot))


def add_basket(name, x, y, z, radius=0.34):
    add_cone(name + "_Body", 10, radius * 0.72, radius, 0.48,
             (x, y, z + 0.24), MAT_LR_Cloth_Cream, COL_PROPS)
    add_cylinder(name + "_Rim", 10, radius * 0.78, 0.05,
                 (x, y, z + 0.48), MAT_LR_Wood_Dark, COL_PROPS)


def add_jar(name, x, y, z, radius=0.22):
    add_sphere(name + "_Body", radius, (x, y, z + radius * 1.1),
               MAT_LR_Stone_Light, COL_PROPS, segments=10, rings=5,
               scale=(1.0, 1.0, 1.15))
    add_cylinder(name + "_Neck", 10, radius * 0.45, radius * 0.7,
                 (x, y, z + radius * 1.9), MAT_LR_Stone_Light, COL_PROPS)


def add_bench(name, x, y, z, facing=1.0):
    add_box(name + "_Seat", (0.62, 2.0, 0.10), (x, y, z + 0.46),
            MAT_LR_Wood_Warm, COL_PROPS)
    add_box(name + "_Back", (0.08, 2.0, 0.52),
            (x + facing * 0.30, y, z + 0.76), MAT_LR_Wood_Warm, COL_PROPS)
    for i, dy in enumerate((-0.78, 0.78)):
        add_box(f"{name}_Leg_{i}", (0.5, 0.10, 0.46),
                (x, y + dy, z + 0.23), MAT_LR_Wood_Dark, COL_PROPS)


def add_banner(name, x, y, z, height=3.6):
    add_cylinder(name + "_Pole", 8, 0.05, height, (x, y, z + height / 2.0),
                 MAT_LR_Wood_Dark, COL_PROPS)
    add_box(name + "_Bar", (0.06, 0.78, 0.06), (x, y, z + height - 0.12),
            MAT_LR_Wood_Dark, COL_PROPS)
    add_box(name + "_Cloth", (0.035, 0.56, 1.85),
            (x + 0.02, y, z + height - 1.12), MAT_BANNER, COL_PROPS)
    add_box(name + "_Hem", (0.045, 0.56, 0.10),
            (x + 0.02, y, z + height - 2.02), MAT_LR_Gold, COL_PROPS)


def add_figure(name, x, y, z, robe=MAT_INDIGO, lantern=False, hat=True):
    add_cone(name + "_Robe", 8, 0.30, 0.15, 1.22,
             (x, y, z + 0.61), robe, COL_PROPS)
    add_sphere(name + "_Head", 0.105, (x, y, z + 1.34),
               MAT_SKIN, COL_PROPS, segments=8, rings=5)
    if hat:
        add_cone(name + "_Hat", 8, 0.20, 0.02, 0.13,
                 (x, y, z + 1.45), MAT_LR_Wood_Dark, COL_PROPS)
    if lantern:
        add_cylinder(name + "_Handle", 4, 0.012, 0.42,
                     (x + 0.26, y, z + 0.86), MAT_LR_Wood_Dark, COL_PROPS)
        add_sphere(name + "_Lantern", 0.11, (x + 0.26, y, z + 0.62),
                   MAT_BULB_WARM, COL_PROPS, segments=8, rings=5,
                   scale=(1.0, 1.0, 1.15))


def add_shoji_pane(name, x, y, z, width, height):
    """A lit shoji panel with a dark frame and lattice, facing south (y-)."""
    add_box(name + "_Frame", (width + 0.16, 0.10, height + 0.16),
            (x, y, z), MAT_LR_Wood_Dark, COL_PROPS)
    add_box(name + "_Pane", (width, 0.12, height),
            (x, y - 0.04, z), MAT_LR_Paper_Glow, COL_PROPS)
    for i in range(1, 3):
        bx = x - width / 2.0 + width * i / 3.0
        add_box(f"{name}_V{i}", (0.035, 0.045, height),
                (bx, y - 0.105, z), MAT_LR_Wood_Dark, COL_PROPS)
    for i in range(1, 4):
        bz = z - height / 2.0 + height * i / 4.0
        add_box(f"{name}_H{i}", (width, 0.045, 0.035),
                (x, y - 0.105, bz), MAT_LR_Wood_Dark, COL_PROPS)


def dress_row_end(side, y_end, index):
    """Finish the exposed side wall at the south end of a shop row.

    The rows start at y=-140; without this the first shop presents a blank
    plaster slab to the whole southern approach and to the 远景 viewpoint.
    """
    tag = "R" if side > 0 else "L"
    shop = bpy.data.objects.get(f"BLD_{tag}_00")
    if shop is None:
        return
    depth = shop.dimensions.x
    height = min(shop.dimensions.z * 0.92, 10.0)
    x0 = side * (RIVER_HALF + PROMENADE)
    x1 = x0 + side * depth
    cx = (x0 + x1) / 2.0
    y = y_end - 0.10
    for x in (x0 + side * 0.12, x1 - side * 0.12):
        add_box(f"PROP_RowEnd_{tag}_{index}_Post_{x:.1f}", (0.20, 0.12, height),
                (x, y, GROUND_Z + height / 2.0), MAT_LR_Wood_Dark, COL_PROPS)
    for level in (0.40, 0.72):
        add_box(f"PROP_RowEnd_{tag}_{index}_Beam_{level}",
                (depth - 0.2, 0.12, 0.14),
                (cx, y, GROUND_Z + height * level),
                MAT_LR_Wood_Dark, COL_PROPS)
    # A timber frame divides the wide side wall into bays; without it the two
    # window rows float on one large plaster slab.
    for i in range(3):
        px = cx + (i - 1) * depth * 0.24
        add_box(f"PROP_RowEnd_{tag}_{index}_MidPost_{i}",
                (0.14, 0.10, height),
                (px, y, GROUND_Z + height / 2.0),
                MAT_LR_Wood_Dark, COL_PROPS)
    add_box(f"PROP_RowEnd_{tag}_{index}_TopBeam",
            (depth - 0.2, 0.12, 0.16),
            (cx, y, GROUND_Z + height * 0.86),
            MAT_LR_Wood_Dark, COL_PROPS)
    for i, bx in enumerate((cx - depth * 0.36, cx + depth * 0.36)):
        add_box(f"PROP_RowEnd_{tag}_{index}_OuterBanner_{i}",
                (0.72, 0.08, 2.20),
                (bx, y - 0.06, GROUND_Z + height * 0.40),
                MAT_BANNER, COL_PROPS)
        add_box(f"PROP_RowEnd_{tag}_{index}_OuterHem_{i}",
                (0.72, 0.10, 0.12),
                (bx, y - 0.06, GROUND_Z + height * 0.40 - 1.14),
                MAT_LR_Gold, COL_PROPS)
    for r, rz in enumerate((0.28, 0.54)):
        for i in range(2):
            wx = cx + (i - 0.5) * depth * 0.36
            add_shoji_pane(f"PROP_RowEnd_{tag}_{index}_Pane_{r}_{i}",
                           wx, y, GROUND_Z + height * rz, 0.92, 1.36)
    add_box(f"PROP_RowEnd_{tag}_{index}_Plinth", (depth + 0.2, 0.16, 0.45),
            (cx, y - 0.03, GROUND_Z + 0.225), MAT_QUAY, COL_PROPS)
    add_box(f"PROP_RowEnd_{tag}_{index}_Eave", (depth + 0.6, 0.95, 0.12),
            (cx, y - 0.40, GROUND_Z + height * 0.64),
            MAT_LR_Roof_Tile, COL_PROPS,
            rotation=(math.radians(-10), 0, 0))
    add_box(f"PROP_RowEnd_{tag}_{index}_EaveUnder", (depth + 0.45, 0.80, 0.08),
            (cx, y - 0.36, GROUND_Z + height * 0.64 - 0.10),
            MAT_LR_Wood_Dark, COL_PROPS,
            rotation=(math.radians(-10), 0, 0))
    for i in range(4):
        bx = cx + (i - 1.5) * depth * 0.24
        add_box(f"PROP_RowEnd_{tag}_{index}_EaveBracket_{i}",
                (0.08, 0.55, 0.08),
                (bx, y - 0.25, GROUND_Z + height * 0.64 - 0.18),
                MAT_LR_Wood_Dark, COL_PROPS)
    add_box(f"PROP_RowEnd_{tag}_{index}_Sign", (0.10, 0.62, 1.9),
            (x0 + side * 0.55, y - 0.16, GROUND_Z + height * 0.46),
            MAT_BANNER, COL_PROPS)
    add_box(f"PROP_RowEnd_{tag}_{index}_SignHem", (0.12, 0.62, 0.12),
            (x0 + side * 0.55, y - 0.16, GROUND_Z + height * 0.46 - 0.92),
            MAT_LR_Gold, COL_PROPS)
    add_box(f"PROP_RowEnd_{tag}_{index}_Bracket", (0.55, 0.08, 0.08),
            (x1 - side * 0.35, y - 0.20, GROUND_Z + 3.2),
            MAT_LR_Wood_Dark, COL_PROPS)
    lantern = instance_kit("SM_Prop_Lantern_Hung_01",
                           f"PROP_RowEnd_{tag}_{index}_Lantern",
                           (x1 - side * 0.62, y - 0.24, GROUND_Z + 3.16),
                           collection=COL_PROPS, scale=0.55)
    if lantern.material_slots:
        lantern.material_slots[0].material = MAT_QUAY_LANTERN
    add_point_light(f"LGT_RowEnd_{tag}_{index}",
                    (x1 - side * 0.62, y - 0.3, GROUND_Z + 2.8),
                    "#FFB066", 24.0, 2.4)
    add_crate(f"PROP_RowEnd_{tag}_{index}_Crate_0", x1 - side * 1.2, y - 0.9,
              GROUND_Z, size=0.70, rot=0.15)
    add_crate(f"PROP_RowEnd_{tag}_{index}_Crate_1", x1 - side * 1.25, y - 1.7,
              GROUND_Z, size=0.55, rot=-0.1)
    add_basket(f"PROP_RowEnd_{tag}_{index}_Basket", x1 - side * 2.1, y - 0.8,
               GROUND_Z)


def add_lantern_rack(name, x, y, z, width=2.4, height=3.1):
    """A red-lantern rack: a bright vertical accent for the empty paving."""
    for s in (-1, 1):
        add_box(f"{name}_Post_{s}", (0.10, 0.10, height),
                (x, y + s * width / 2.0, z + height / 2.0),
                MAT_LR_Wood_Dark, COL_PROPS)
        add_box(f"{name}_Foot_{s}", (0.45, 0.45, 0.10),
                (x, y + s * width / 2.0, z + 0.05),
                MAT_LR_Stone_Light, COL_PROPS)
    add_box(f"{name}_Beam", (0.10, width + 0.3, 0.10),
            (x, y, z + height), MAT_LR_Wood_Dark, COL_PROPS)
    add_box(f"{name}_Roof", (0.82, width + 0.55, 0.12),
            (x, y, z + height + 0.16), MAT_LR_Roof_Tile, COL_PROPS)
    add_box(f"{name}_RoofUnder", (0.72, width + 0.45, 0.06),
            (x, y, z + height + 0.08), MAT_LR_Wood_Dark, COL_PROPS)
    for i in range(3):
        ly = y + (i - 1) * (width / 3.0)
        add_cylinder(f"{name}_Cord_{i}", 4, 0.012, 0.42,
                     (x, ly, z + height - 0.26),
                     MAT_LR_Wood_Dark, COL_PROPS)
        add_sphere(f"{name}_Lantern_{i}", 0.24,
                   (x, ly, z + height - 0.64), MAT_BULB_RED, COL_PROPS,
                   segments=10, rings=6, scale=(1.0, 1.0, 1.25))
        add_cylinder(f"{name}_Cap_{i}", 6, 0.12, 0.05,
                     (x, ly, z + height - 0.38), MAT_LR_Gold, COL_PROPS)


def add_stone_lantern(name, x, y, z, scale=1.0):
    """A six-sided stone lantern: plinth, shaft, lit chamber and flared cap."""
    s = scale
    add_box(f"{name}_Base", (0.78 * s, 0.78 * s, 0.20 * s),
            (x, y, z + 0.10 * s), MAT_QUAY, COL_PROPS)
    add_cylinder(f"{name}_Shaft", 6, 0.13 * s, 0.95 * s,
                 (x, y, z + 0.68 * s), MAT_LR_Stone_Light, COL_PROPS)
    add_cylinder(f"{name}_Plate", 6, 0.34 * s, 0.10 * s,
                 (x, y, z + 1.18 * s), MAT_LR_Stone_Light, COL_PROPS)
    # A dark stone chamber with four glowing paper panes, one per face.
    add_box(f"{name}_Chamber", (0.46 * s, 0.46 * s, 0.44 * s),
            (x, y, z + 1.44 * s), MAT_QUAY, COL_PROPS)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        add_box(f"{name}_Pane_{dx}_{dy}",
                (0.30 * s if dy else 0.05 * s,
                 0.30 * s if dx else 0.05 * s, 0.30 * s),
                (x + dx * 0.245 * s, y + dy * 0.245 * s, z + 1.44 * s),
                MAT_LR_Paper_Glow, COL_PROPS)
    add_cone(f"{name}_Cap", 6, 0.46 * s, 0.10 * s, 0.30 * s,
             (x, y, z + 1.80 * s), MAT_LR_Roof_Tile, COL_PROPS)
    add_sphere(f"{name}_Finial", 0.09 * s, (x, y, z + 1.98 * s),
               MAT_LR_Gold, COL_PROPS, segments=8, rings=4)


def add_hanging_sign(name, side, y, z, height=1.5, mat=MAT_BANNER):
    """A shop signboard on a bracket, projecting into the street.

    The board is thin in y so walkers read it edge-on down the row, the way a
    real 幌子 works: a bright vertical accent every few bays.
    """
    wall_x = side * (RIVER_HALF + PROMENADE - 0.15)
    board_x = wall_x - side * 0.72
    add_box(f"{name}_Arm", (0.92, 0.07, 0.07),
            (wall_x - side * 0.46, y, z + height * 0.5),
            MAT_LR_Wood_Dark, COL_PROPS)
    add_box(f"{name}_Board", (0.55, 0.08, height),
            (board_x, y, z), mat, COL_PROPS)
    add_box(f"{name}_Cap", (0.64, 0.17, 0.09),
            (board_x, y, z + height * 0.5 + 0.05),
            MAT_LR_Roof_Tile, COL_PROPS)
    add_box(f"{name}_Hem", (0.57, 0.10, 0.10),
            (board_x, y, z - height * 0.5), MAT_LR_Gold, COL_PROPS)
    add_box(f"{name}_Seal", (0.22, 0.11, 0.24),
            (board_x, y, z + height * 0.16), MAT_LR_Gold, COL_PROPS)


def add_tea_cart(name, x, y, z, facing=1.0):
    """A two-wheel tea cart under a cream canopy; a working-street silhouette."""
    add_box(f"{name}_Body", (0.95, 1.7, 0.72),
            (x, y, z + 0.62), MAT_LR_Wood_Warm, COL_PROPS)
    add_box(f"{name}_Top", (1.05, 1.8, 0.08),
            (x, y, z + 1.02), MAT_LR_Wood_Dark, COL_PROPS)
    for s in (-1, 1):
        add_cylinder(f"{name}_Wheel_{s}", 12, 0.38, 0.08,
                     (x + s * 0.52, y, z + 0.42),
                     MAT_LR_Wood_Dark, COL_PROPS,
                     rotation=(0, math.pi / 2, 0))
    for sx in (-1, 1):
        for sy in (-1, 1):
            add_box(f"{name}_Post_{sx}_{sy}", (0.06, 0.06, 1.55),
                    (x + sx * 0.42, y + sy * 0.72, z + 1.85),
                    MAT_LR_Wood_Dark, COL_PROPS)
    add_box(f"{name}_Canopy", (1.15, 1.75, 0.07),
            (x, y, z + 2.65), MAT_LR_Cloth_Cream, COL_PROPS)
    add_box(f"{name}_CanopyTrim", (1.20, 1.80, 0.05),
            (x, y, z + 2.60), MAT_BANNER, COL_PROPS)
    add_sphere(f"{name}_Lantern", 0.14,
               (x + facing * 0.55, y + 0.6, z + 2.18), MAT_BULB_WARM,
               COL_PROPS, segments=8, rings=5, scale=(1.0, 1.0, 1.2))
    add_jar(f"{name}_Jar_0", x + facing * 0.1, y - 0.55, z + 1.06, radius=0.16)
    add_basket(f"{name}_Basket", x - facing * 0.1, y + 0.55, z + 1.06,
               radius=0.20)


prop_rng = random.Random(SEED + 606)
for i, (side, y, _kind) in enumerate(stall_specs):
    facade_x = side * (RIVER_HALF + PROMENADE)
    inner_x = facade_x - side * 1.0
    add_barrel(f"PROP_Barrel_{i}_0", inner_x, y - 2.4, GROUND_Z,
               scale=prop_rng.uniform(0.85, 1.1))
    add_crate(f"PROP_Crate_{i}_0", inner_x - side * 0.2, y + 2.3, GROUND_Z,
              size=prop_rng.uniform(0.55, 0.75),
              rot=prop_rng.uniform(-0.2, 0.2))
    if i % 2 == 0:
        add_basket(f"PROP_Basket_{i}", inner_x + side * 0.1, y + 2.9, GROUND_Z)
    if i % 3 == 0:
        add_jar(f"PROP_Jar_{i}", inner_x - side * 0.1, y - 2.9, GROUND_Z)
    add_figure(f"PROP_Figure_Stall_{i}", side * 16.9,
               y + prop_rng.uniform(-1.6, 1.6), GROUND_Z,
               robe=MAT_INDIGO if i % 2 else MAT_PLUM,
               lantern=(i % 5 == 0))

# Benches face the water along the quay.
for i, y in enumerate((-114.0, -76.0, -34.0, 16.0, 60.0, 104.0, 144.0)):
    for side in (-1, 1):
        add_bench(f"PROP_Bench_{'R' if side > 0 else 'L'}_{i}",
                  side * 13.9, y, GROUND_Z, facing=side)

# Vertical banners give the facades a warm colour rhythm.
for i, y in enumerate((-122.0, -98.0, -72.0, -46.0, -20.0, 24.0, 52.0,
                       78.0, 104.0, 130.0, 156.0)):
    for side in (-1, 1):
        if side > 0 and 24.0 < y < 90.0:
            continue
        add_banner(f"PROP_Banner_{'R' if side > 0 else 'L'}_{i}",
                   side * 19.2, y, GROUND_Z,
                   height=prop_rng.uniform(3.2, 4.0))

# Potted plants flank the gate and the plaza approach.
for i, (x, y) in enumerate(((17.0, -126.0), (15.2, -114.0),
                            (-17.0, -126.0), (-15.2, -114.0),
                            (24.0, 50.0), (24.0, 74.0))):
    add_cylinder(f"PROP_Pot_{i}", 8, 0.28, 0.42,
                 (x, y, GROUND_Z + 0.21), MAT_LR_Stone_Light, COL_PROPS)
    build_shrub(f"PROP_PotPlant_{i}", (x, y, GROUND_Z + 0.80), size=0.95,
                count=9, seed=SEED + i * 7, collection=COL_PROPS)

# A handful of people on the street, mostly silhouettes with a warm lantern.
for i, (x, y) in enumerate(((0.0, -8.0), (0.0, 28.0), (16.0, -100.0),
                            (-16.0, -80.0), (16.0, 120.0), (-16.0, 140.0))):
    add_figure(f"PROP_Figure_Street_{i}", x, y, GROUND_Z,
               robe=MAT_INDIGO if i % 2 else MAT_PLUM, lantern=True)

# Finish the exposed south walls of both shop rows; the 远景 camera looks
# straight down the east promenade at the first shop's blank side.
for side in (-1, 1):
    dress_row_end(side, -140.0, 0)

# Lantern racks fill the gaps between stalls with a strong red rhythm.
for i, (side, y) in enumerate(((1, -132.0), (1, -94.0), (1, -56.0),
                               (1, 12.0), (1, 72.0), (1, 110.0),
                               (-1, -122.0), (-1, -88.0), (-1, -58.0),
                               (-1, -12.0), (-1, 76.0), (-1, 142.0))):
    add_lantern_rack(f"PROP_LanternRack_{i}", side * 14.2, y, GROUND_Z)
    if i % 2 == 0:
        add_point_light(f"LGT_LanternRack_{i}", (side * 14.2, y, GROUND_Z + 2.4),
                        "#FF8A4A", 22.0, 2.4)

# Projecting shop signs give the facade line a bright vertical rhythm at head
# height.  They skip the bridge opening and the plaza frontage.
BANNER_Y = (-122.0, -98.0, -72.0, -46.0, -20.0, 24.0, 52.0,
            78.0, 104.0, 130.0, 156.0)
sign_mats = (MAT_BANNER, MAT_LR_Cloth_Cream, MAT_INDIGO)
sign_index = 0
for side in (-1, 1):
    for step in range(-134, 176, 13):
        y = float(step)
        if -4.0 <= y <= 24.0:
            continue
        if side > 0 and 24.0 <= y <= 90.0:
            continue
        if any(abs(y - by) < 4.0 for by in BANNER_Y):
            continue
        add_hanging_sign(
            f"PROP_ShopSign_{'R' if side > 0 else 'L'}_{sign_index}",
            side, y, GROUND_Z + 4.05,
            height=prop_rng.uniform(1.15, 1.50),
            mat=sign_mats[sign_index % 3],
        )
        sign_index += 1

# Stone lanterns mark the approach, the bridgeheads, the plaza and the far end.
for i, (x, y, s) in enumerate((
    (14.2, -148.0, 1.00), (-14.2, -148.0, 1.00),
    (14.2, -156.0, 0.92), (-14.2, -156.0, 0.92),
    (13.9, 2.0, 0.95), (-13.9, 2.0, 0.95),
    (13.9, 18.0, 0.95), (-13.9, 18.0, 0.95),
    (23.6, 47.0, 1.00), (23.6, 79.0, 1.00),
    (14.2, 172.0, 0.95), (-14.2, 172.0, 0.95),
)):
    add_stone_lantern(f"PROP_StoneLantern_{i}", x, y, GROUND_Z, scale=s)

# Tall banner poles frame the southern approach seen from the 远景 viewpoint.
for side in (-1, 1):
    px = side * 18.4
    add_cylinder(f"PROP_ApproachPole_{side}", 8, 0.10, 6.4,
                 (px, -150.0, GROUND_Z + 3.2),
                 MAT_LR_Wood_Dark, COL_PROPS)
    add_box(f"PROP_ApproachArm_{side}", (0.85, 0.08, 0.08),
            (px - side * 0.42, -150.0, GROUND_Z + 6.0),
            MAT_LR_Wood_Dark, COL_PROPS)
    approach_lantern = instance_kit(
        "SM_Prop_Lantern_Hung_01", f"PROP_ApproachLantern_{side}",
        (px - side * 0.80, -150.0, GROUND_Z + 5.85),
        collection=COL_PROPS, scale=0.9)
    if approach_lantern.material_slots:
        approach_lantern.material_slots[0].material = MAT_QUAY_LANTERN
    add_point_light(f"LGT_Approach_{side}",
                    (px - side * 0.80, -150.0, GROUND_Z + 5.2),
                    "#FF9A55", 26.0, 3.2)

# Festival crowd: pairs and small groups in the walking lane.
crowd_spots = ((15.5, -96.0), (15.9, -91.5), (-15.5, -64.0), (-15.2, -59.0),
               (15.4, -22.0), (15.9, -17.0), (-15.4, 8.0), (-15.9, 13.0),
               (15.3, 63.0), (15.8, 68.5), (-15.4, 96.0), (-15.9, 101.0),
               (15.3, 136.0), (15.8, 141.0), (-15.3, 166.0), (-15.9, 171.0))
for i, (x, y) in enumerate(crowd_spots):
    add_figure(f"PROP_Figure_Crowd_{i}", x, y, GROUND_Z,
               robe=(MAT_INDIGO, MAT_PLUM, MAT_CREAM)[i % 3],
               lantern=(i % 3 == 0), hat=(i % 4 != 0))

# Working tea carts in the wider gaps between stalls.
for i, (side, y) in enumerate(((1, -30.0), (1, 112.0), (-1, 92.0))):
    add_tea_cart(f"PROP_TeaCart_{i}", side * 17.0, y, GROUND_Z, facing=-side)
    add_figure(f"PROP_Figure_Cart_{i}", side * 16.0, y + 1.4, GROUND_Z,
               robe=MAT_CREAM if i % 2 else MAT_INDIGO, lantern=False)

# A few more pots and benches at the quiet ends of the promenade.
for i, (x, y) in enumerate(((17.0, -92.0), (15.2, -70.0), (-17.0, -44.0),
                            (-15.2, 8.0), (17.0, 62.0), (15.2, 88.0),
                            (-17.0, 118.0), (-15.2, 158.0))):
    add_cylinder(f"PROP_PotExtra_{i}", 8, 0.28, 0.42,
                 (x, y, GROUND_Z + 0.21), MAT_LR_Stone_Light, COL_PROPS)
    build_shrub(f"PROP_PotExtraPlant_{i}", (x, y, GROUND_Z + 0.80), size=0.95,
                count=9, seed=SEED + 300 + i * 7, collection=COL_PROPS)
for i, y in enumerate((-136.0, -54.0, 36.0, 124.0)):
    for side in (-1, 1):
        add_bench(f"PROP_BenchExtra_{'R' if side > 0 else 'L'}_{i}",
                  side * 13.9, y, GROUND_Z, facing=side)

# Quay lantern posts: human-scale warmth and a rhythm along both banks.
def quay_post(side, y, index):
    px = side * (RIVER_HALF + 0.35)
    add_cylinder(f"PROP_QuayPost_{side}_{index}", 8, 0.075, 3.8,
                 (px, y, GROUND_Z + 1.9), bpy.data.materials["MAT_LR_Wood_Dark"],
                 COL_PROPS)
    # The arm reaches inland so the lantern lights the promenade it stands on.
    add_box(f"PROP_QuayArm_{side}_{index}", (0.9, 0.10, 0.10),
            (px + side * 0.40, y, GROUND_Z + 3.74),
            bpy.data.materials["MAT_LR_Wood_Dark"], COL_PROPS)
    lantern = instance_kit("SM_Prop_Lantern_Hung_01", f"PROP_QuayLantern_{side}_{index}",
                           (px + side * 0.80, y, GROUND_Z + 3.70),
                           collection=COL_PROPS, scale=0.85)
    if lantern.material_slots:
        lantern.material_slots[0].material = MAT_QUAY_LANTERN
    return lantern


QUAY_POST_Y = (-118.0, -88.0, -58.0, -28.0, 26.0, 56.0, 86.0, 126.0, 156.0)
for side in (-1, 1):
    for j, y in enumerate(QUAY_POST_Y):
        quay_post(side, y, j)


# Lanterns under the shop eaves: a second, lower rhythm at eye level.  The
# bracket reaches out of the facade so the lantern hangs clear of the wall.
def eave_lantern(side, y, index):
    x = side * (RIVER_HALF + PROMENADE - 0.22)
    add_box(f"PROP_EaveBracket_{side}_{index}", (0.50, 0.08, 0.08),
            (x - side * 0.22, y, GROUND_Z + 4.32),
            bpy.data.materials["MAT_LR_Wood_Dark"], COL_PROPS)
    lantern = instance_kit("SM_Prop_Lantern_Hung_01",
                           f"PROP_EaveLantern_{side}_{index}",
                           (x - side * 0.42, y, GROUND_Z + 4.28),
                           collection=COL_PROPS, scale=0.62)
    if lantern.material_slots:
        lantern.material_slots[0].material = MAT_QUAY_LANTERN
    if index % 4 == 0:
        add_point_light(f"LGT_Eave_{side}_{index}",
                        (x - side * 0.42, y, GROUND_Z + 3.8),
                        "#FFB066", 32.0, 3.0)
    return lantern


for side in (-1, 1):
    index = 0
    for y in range(-136, 172, 11):
        if -4 <= y <= 24:
            continue
        if side > 0 and 24 <= y <= 90:
            continue
        eave_lantern(side, float(y), index)
        index += 1


# Bridge lanterns follow the arch, one pair every 4 m.
def bridge_deck_z(x):
    return GROUND_Z + 0.2 + 4.15 * (1.0 - (x / 18.0) ** 2)


for i, x in enumerate((-16.0, -12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0, 16.0)):
    z = bridge_deck_z(x)
    for side in (-1, 1):
        y = BRIDGE_Y + side * 2.9
        add_cylinder(f"PROP_BridgeLanternPost_{i}_{side}", 6, 0.035, 0.9,
                     (x, y, z + 0.45), bpy.data.materials["MAT_LR_Wood_Dark"],
                     COL_PROPS)
        add_sphere(f"PROP_BridgeLantern_{i}_{side}", 0.15,
                   (x, y, z + 0.92), MAT_BULB_WARM, COL_PROPS,
                   segments=8, rings=5, scale=(1.0, 1.0, 1.2))
for i, x in enumerate((-12.0, -4.0, 4.0, 12.0)):
    for side in (-1, 1):
        add_point_light(f"LGT_BridgeLantern_{i}_{side}",
                        (x, BRIDGE_Y + side * 2.9, bridge_deck_z(x) + 0.9),
                        "#FFB36A", 30.0, 2.0)

# ---------------------------------------------------------------------------
# Lantern strings
# ---------------------------------------------------------------------------

def river_string(name, y, height=6.1, sag=1.7, spacing=1.55, red_lanterns=True):
    """One string across the whole street, tied into the shopfronts.

    The ends land on the upper facade, so the wire reads as hung between
    buildings instead of floating above the roofs, and the lanterns clear eye
    level far enough that they read as a canopy rather than nearby moons.
    """
    edge = RIVER_HALF + PROMENADE + 0.05
    span = edge * 2.0
    count = max(8, int(span / spacing))
    pts = []
    for i in range(count + 1):
        t = i / count
        x = -edge + span * t
        z = height - sag * 4 * t * (1 - t)
        pts.append((x, y, z))
    add_curve_tube(name + "_Wire", pts, 0.012, bpy.data.materials["MAT_LR_Wood_Dark"],
                   COL_PROPS, resolution_u=2, bevel_resolution=1)
    for i in range(1, count):
        t = i / count
        x = -edge + span * t
        z = height - sag * 4 * t * (1 - t) - 0.14
        if red_lanterns and i % 7 == 3:
            add_sphere(f"{name}_Red_{i}", 0.19, (x, y, z - 0.10), MAT_BULB_RED,
                       COL_PROPS, segments=8, rings=4, scale=(1.0, 1.0, 1.25))
        elif i % 11 == 6:
            add_sphere(f"{name}_Gold_{i}", 0.13, (x, y, z), MAT_BULB_GOLD,
                       COL_PROPS, segments=8, rings=4)
        else:
            add_sphere(f"{name}_Bulb_{i}", 0.10, (x, y, z), MAT_BULB_WARM,
                       COL_PROPS, segments=8, rings=4)


def cross_river_string(name, y_east, y_west, height=5.6, sag=1.2):
    """A diagonal string from one bank to the other.

    Straight cross-river rows alone read as parallel rails; the diagonals
    weave the overhead layer the reference uses to build depth.
    """
    edge = RIVER_HALF + PROMENADE + 0.05
    count = 24
    pts = []
    for i in range(count + 1):
        t = i / count
        pts.append((edge - 2.0 * edge * t,
                    y_east + (y_west - y_east) * t,
                    height - sag * 4 * t * (1 - t)))
    add_curve_tube(name + "_Wire", pts, 0.012,
                   MAT_LR_Wood_Dark, COL_PROPS,
                   resolution_u=2, bevel_resolution=1)
    for i in range(1, count):
        t = i / count
        x = edge - 2.0 * edge * t
        yy = y_east + (y_west - y_east) * t
        zz = height - sag * 4 * t * (1 - t) - 0.12
        if i % 6 == 3:
            add_sphere(f"{name}_Red_{i}", 0.19, (x, yy, zz), MAT_BULB_RED,
                       COL_PROPS, segments=8, rings=4, scale=(1.0, 1.0, 1.25))
        elif i % 5 == 2:
            add_sphere(f"{name}_Gold_{i}", 0.11, (x, yy, zz), MAT_BULB_GOLD,
                       COL_PROPS, segments=8, rings=4)
        else:
            add_sphere(f"{name}_Bulb_{i}", 0.09, (x, yy, zz), MAT_BULB_WARM,
                       COL_PROPS, segments=8, rings=4)


# Pick y values that sit inside a shophouse on both banks, clear of the bridge
# and the tower island.  A string every 16-20 m gives the canal the layered
# overhead rhythm of the reference instead of one lonely line.
for i, y in enumerate((-128.0, -112.0, -96.0, -78.0, -60.0, -42.0, -15.0,
                       2.0, 20.0, 34.0, 52.0, 68.0, 89.0, 102.0, 115.0,
                       132.0, 149.0, 162.0)):
    river_string(f"PROP_RiverString_{i}", y, height=6.1 + (i % 2) * 0.22,
                 spacing=1.35)

# Diagonal strings weave through the straight rows so the canopy of lights
# reads as a layered net instead of parallel rails.
for i, (ye, yw, h) in enumerate(((-124.0, -116.0, 5.6),
                                 (-76.0, -68.0, 6.8),
                                 (-32.0, -24.0, 6.0),
                                 (26.0, 34.0, 7.0),
                                 (82.0, 90.0, 5.8),
                                 (138.0, 146.0, 6.6))):
    cross_river_string(f"PROP_CrossString_{i}", ye, yw, height=h, sag=1.1)

# Low strings between the quay posts: supported at both ends, and high enough
# to keep the lanterns above head height along the promenade.
for side in (-1, 1):
    x = side * (RIVER_HALF + 0.35)
    for j, (a, b) in enumerate(zip(QUAY_POST_Y, QUAY_POST_Y[1:])):
        sag = 0.32
        pts = [(x, a, GROUND_Z + 3.80), (x, (a + b) / 2, GROUND_Z + 3.80 - sag),
               (x, b, GROUND_Z + 3.80)]
        add_curve_tube(f"PROP_BankWire_{side}_{j}", pts, 0.011,
                       bpy.data.materials["MAT_LR_Wood_Dark"], COL_PROPS)
        bulbs = max(4, int((b - a) / 2.0))
        for k in range(1, bulbs):
            t = k / bulbs
            yy = a + (b - a) * t
            zz = GROUND_Z + 3.80 - sag * 4 * t * (1 - t) - 0.1
            add_sphere(f"PROP_BankBulb_{side}_{j}_{k}", 0.11, (x, yy, zz),
                       MAT_BULB_WARM, COL_PROPS, segments=8, rings=4)

# ---------------------------------------------------------------------------
# Sky lanterns and river lights
# ---------------------------------------------------------------------------

def scatter_sky_lanterns():
    rng = random.Random(SEED + 77)
    for i in range(95):
        x = rng.uniform(-65, 65)
        y = rng.uniform(-10, 190)
        z = rng.uniform(22, 62) + max(0.0, (y + 10) / 200.0) * 8
        s = rng.uniform(0.28, 0.58)
        instance_kit("SM_Prop_Lantern_Sky_01", f"FX_SkyLantern_{i:03d}",
                     (x, y, z), rot_z=rng.uniform(0, math.tau), scale=s,
                     collection=COL_FX)


scatter_sky_lanterns()

# Low floating river lights near the quays.  A denser drift under the bridge
# and the tower gives the water the same layered warmth as the sky.
rng = random.Random(SEED + 101)
for i in range(64):
    side = rng.choice((-1, 1))
    x = side * rng.uniform(RIVER_HALF - 4.0, RIVER_HALF - 0.6)
    y = rng.uniform(-120.0, 170.0)
    if i % 5 == 0:
        y = rng.uniform(2.0, 22.0)
    elif i % 7 == 0:
        y = rng.uniform(66.0, 90.0)
    material = (MAT_BULB_RED if i % 7 == 3
                else MAT_BULB_GOLD if i % 5 == 1
                else MAT_BULB_WARM)
    add_sphere(f"FX_RiverLight_{i}", 0.12, (x, y, 0.07), material,
               COL_FX, segments=8, rings=4, scale=(1.0, 1.0, 0.5))

# Lotus beds and reed clumps soften the hard quay edge and add near-water
# detail at eye height.
lotus_rng = random.Random(SEED + 909)
for i in range(22):
    side = lotus_rng.choice((-1, 1))
    x = side * lotus_rng.uniform(RIVER_HALF - 2.6, RIVER_HALF - 0.7)
    y = lotus_rng.uniform(-120.0, 165.0)
    for j in range(lotus_rng.randint(3, 5)):
        add_cylinder(f"PROP_LotusLeaf_{i}_{j}", 8,
                     lotus_rng.uniform(0.34, 0.62), 0.025,
                     (x + lotus_rng.uniform(-1.0, 1.0),
                      y + lotus_rng.uniform(-1.6, 1.6), 0.07),
                     MAT_LOTUS_LEAF, COL_PROPS)
    for j in range(lotus_rng.randint(1, 2)):
        add_cone(f"PROP_LotusFlower_{i}_{j}", 6, 0.18, 0.02, 0.34,
                 (x + lotus_rng.uniform(-0.7, 0.7),
                  y + lotus_rng.uniform(-1.0, 1.0), 0.24),
                 MAT_LOTUS_FLOWER, COL_PROPS)
    if i % 3 == 0:
        for j in range(5):
            add_cylinder(f"PROP_Reed_{i}_{j}", 4, 0.015,
                         lotus_rng.uniform(0.8, 1.5),
                         (x + lotus_rng.uniform(-0.8, 0.8),
                          y + lotus_rng.uniform(-1.2, 1.2), 0.5),
                         MAT_REED, COL_PROPS)

# ---------------------------------------------------------------------------
# Boats
# ---------------------------------------------------------------------------

def build_boat(name, location, rot_z=0.0, scale=1.0):
    """Detailed kit boat, instanced three times along the river."""
    obj = instance_kit("SM_Prop_Boat_Pleasure_01", name, location,
                       rot_z=rot_z, scale=scale, collection=COL_PROPS)
    # The boat shares its mesh with the kit, so override only this object's
    # paper slot to keep the cabin windows readable against dark water.
    for slot in obj.material_slots:
        if slot.material and slot.material.name == "MAT_LR_Paper_Glow":
            slot.link = "OBJECT"
            slot.material = MAT_BOAT_PAPER
    # Warm bow lantern light, one per boat.
    add_point_light(f"LGT_{name}", (location[0], location[1], 2.0 * scale),
                    "#FFB066", 130.0, 1.2)
    # Soft top light reveals the tiled cabin roof instead of a black silhouette.
    add_area_light(f"LGT_{name}_Top", (location[0], location[1], 5.2 * scale),
                   (location[0], location[1], 0.8), "#FFB877", 90, 3.2)
    # Camera-side fill lifts the hull and sheer without touching the emissive paper.
    add_area_light(f"LGT_{name}_Side", (location[0] - 7.0, location[1] - 9.0, 4.2),
                   (location[0], location[1], 1.2), "#FFC08A", 120, 9.0)
    return obj


build_boat("PROP_Boat_01", (7.0, -26.0, 0.0), rot_z=0.35, scale=1.0)
build_boat("PROP_Boat_02", (-8.5, 52.0, 0.0), rot_z=-0.5, scale=0.85)
build_boat("PROP_Boat_03", (7.0, 96.0, 0.0), rot_z=0.18, scale=1.15)
build_boat("PROP_Boat_04", (5.8, 66.0, 0.0), rot_z=0.24, scale=0.92)
build_boat("PROP_Boat_05", (-6.2, -8.0, 0.0), rot_z=2.85, scale=0.88)

# Moored skiffs fill the near water and give the docks a reason to exist.
for i, (x, y, rot, scale) in enumerate((
    (10.2, -58.0, 1.25, 1.0),
    (-10.2, 30.0, -1.1, 0.92),
    (10.6, 140.0, 0.4, 1.08),
    (-9.8, -115.0, 2.4, 0.95),
)):
    instance_kit("SRC_Skiff", f"PROP_Skiff_{i}", (x, y, 0.05),
                 rot_z=rot, scale=scale, collection=COL_PROPS)
    add_curve_tube(f"PROP_SkiffRope_{i}",
                   [(x, y, 0.55), (x + (1.4 if x > 0 else -1.4), y + 0.6, 0.9),
                    (12.85 if x > 0 else -12.85, y + 1.2, GROUND_Z + 0.9)],
                   0.018, bpy.data.materials["MAT_LR_Wood_Dark"], COL_PROPS,
                   resolution_u=2, bevel_resolution=1)

# The 打铁花 interaction needs a visible stage across the river.  The authored
# performance pavilion is set against the west shopfronts at 0.62 scale so the
# promenade keeps a walking lane in front of it.
stage = instance_kit("SRC_Performance", "PROP_PerformanceStage",
                     (-17.2, 26.0, GROUND_Z), rot_z=-math.pi / 2,
                     scale=0.62, collection=COL_PROPS)
add_box("PROP_PerformanceApron", (1.5, 8.2, 0.06),
        (-13.7, 26.0, GROUND_Z + 0.03), MAT_LR_Lacquer_Red, COL_PROPS)
add_point_light("LGT_PerformanceStage", (-14.3, 26.0, 3.0),
                "#FF9A55", 60.0, 4.0)
add_area_light("LGT_PerformanceWash", (-12.8, 26.0, 4.6),
               (-17.2, 26.0, 2.0), "#FFB877", 260, 6)
for i, y in enumerate((21.5, 23.5, 25.5, 27.5, 29.5, 31.5)):
    add_figure(f"PROP_StageFigure_{i}", -13.2, y, GROUND_Z,
               robe=MAT_INDIGO if i % 2 else MAT_PLUM, lantern=(i % 3 == 0))

# Ferry docks replace the bare water steps and add a lit landing on each bank.
instance_kit("SRC_FerryDock", "PROP_FerryDock_E", (13.4, -48.0, 0.55),
             rot_z=-math.pi / 2, collection=COL_PROPS)
instance_kit("SRC_FerryDock", "PROP_FerryDock_W", (-15.4, -90.0, 0.55),
             rot_z=math.pi / 2, collection=COL_PROPS)
add_point_light("LGT_FerryDock_E", (15.0, -48.0, 3.0), "#FFB066", 70.0, 3.0)
add_point_light("LGT_FerryDock_W", (-15.0, -90.0, 3.0), "#FFB066", 70.0, 3.0)

# ---------------------------------------------------------------------------
# Cherry trees, willows and their foliage cards
# ---------------------------------------------------------------------------



def add_tube_geometry(verts, faces, points, radii, sides=6):
    """Append a tapered tube along a polyline into shared buffers.

    Parallel transport keeps the rings from twisting where the branch bends,
    which a per-point `to_track_quat` does not.
    """
    count = len(points)
    tangents = []
    for i in range(count):
        a = points[max(0, i - 1)]
        b = points[min(count - 1, i + 1)]
        tangents.append((b - a).normalized())

    normal = tangents[0].orthogonal().normalized()
    base = len(verts)
    for i in range(count):
        if i:
            quat = tangents[i - 1].rotation_difference(tangents[i])
            normal = quat @ normal
            normal = (normal - tangents[i] * normal.dot(tangents[i])).normalized()
        tangent = tangents[i]
        bitangent = tangent.cross(normal)
        radius = radii[min(i, len(radii) - 1)]
        for j in range(sides):
            angle = math.tau * j / sides
            verts.append(tuple(points[i] + normal * (math.cos(angle) * radius)
                               + bitangent * (math.sin(angle) * radius)))

    for i in range(count - 1):
        for j in range(sides):
            a = base + i * sides + j
            b = base + i * sides + (j + 1) % sides
            faces.append((a, b, b + sides, a + sides))

    tip = len(verts)
    verts.append(tuple(points[-1]))
    for j in range(sides):
        a = base + (count - 1) * sides + j
        faces.append((a, base + (count - 1) * sides + (j + 1) % sides, tip))


def make_tube_object(name, verts, faces, material, collection):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def _polyline(start, direction, length, steps, rng, spread):
    """Walk a wobbly polyline, so limbs bend instead of being straight sticks."""
    points = [start]
    heading = direction.normalized()
    for _ in range(steps):
        heading = (heading + Vector((rng.uniform(-spread, spread),
                                     rng.uniform(-spread, spread),
                                     rng.uniform(-spread * 0.3, spread * 0.45)))).normalized()
        points.append(points[-1] + heading * (length / steps))
    return points


def _point_on(points, t):
    span = len(points) - 1
    x = min(span - 1e-4, max(0.0, t * span))
    index = int(x)
    return points[index].lerp(points[index + 1], x - index)


def build_cherry_tree(name, location, scale=1.0, seed=0):
    """A blossom tree built from a tapered skeleton and foliage cards.

    Solid puffs read as fruit at first-person distance.  The card carries the
    blossom silhouette in its texture, so a five-hundred-quad canopy reads as a
    mass of flowers while costing a fraction of the old sphere count.
    """
    rng = random.Random(seed)
    base = Vector(location)
    cards = []

    def scatter(centre, size):
        cards.append((centre, size, _card_rotation(rng),
                      rng.randrange(4), rng.randrange(4), rng.random() < 0.5))

    # Trunk stays its own object: the collision export looks for <name>_Trunk.
    trunk_pts = _polyline(base, Vector((0.0, 0.0, 1.0)), 1.75 * scale, 3, rng, 0.09)
    trunk_v, trunk_f = [], []
    add_tube_geometry(trunk_v, trunk_f, trunk_pts,
                      [0.155 * scale, 0.14 * scale, 0.122 * scale, 0.105 * scale], 7)
    make_tube_object(f"{name}_Trunk", trunk_v, trunk_f, MAT_BARK, COL_TREES)

    branch_v, branch_f = [], []
    for i in range(4):
        angle = math.tau * i / 4 + rng.uniform(-0.32, 0.32)
        start = _point_on(trunk_pts, rng.uniform(0.60, 0.90))
        heading = Vector((math.cos(angle), math.sin(angle),
                          rng.uniform(1.05, 1.65))).normalized()
        limb = _polyline(start, heading, rng.uniform(1.15, 1.45) * scale, 3, rng, 0.20)
        add_tube_geometry(branch_v, branch_f, limb,
                          [0.095 * scale, 0.082 * scale, 0.066 * scale, 0.046 * scale], 6)

        for s in range(3):
            sub_angle = angle + rng.uniform(-0.95, 0.95)
            sub_heading = (heading + Vector((math.cos(sub_angle) * 0.9,
                                             math.sin(sub_angle) * 0.9,
                                             rng.uniform(0.35, 1.05)))).normalized()
            sub = _polyline(_point_on(limb, 0.45 + s * 0.26), sub_heading,
                            rng.uniform(0.78, 1.02) * scale, 2, rng, 0.24)
            add_tube_geometry(branch_v, branch_f, sub,
                              [0.045 * scale, 0.034 * scale, 0.023 * scale], 5)

            for _ in range(6):
                anchor = _point_on(sub, rng.uniform(0.45, 1.05))
                scatter(anchor + Vector((rng.uniform(-0.30, 0.30),
                                         rng.uniform(-0.30, 0.30),
                                         rng.uniform(-0.16, 0.28))) * scale,
                        rng.uniform(0.52, 0.78) * scale)

            for k in range(2):
                twig_heading = (sub_heading + Vector((rng.uniform(-0.85, 0.85),
                                                      rng.uniform(-0.85, 0.85),
                                                      rng.uniform(0.30, 1.05)))).normalized()
                twig = _polyline(_point_on(sub, 0.55 + 0.45 * k), twig_heading,
                                 rng.uniform(0.50, 0.72) * scale, 2, rng, 0.28)
                add_tube_geometry(branch_v, branch_f, twig,
                                  [0.020 * scale, 0.013 * scale, 0.007 * scale], 4)
                for _ in range(8):
                    anchor = _point_on(twig, rng.uniform(0.15, 1.05))
                    scatter(anchor + Vector((rng.uniform(-0.22, 0.22),
                                             rng.uniform(-0.22, 0.22),
                                             rng.uniform(-0.12, 0.24))) * scale,
                            rng.uniform(0.50, 0.76) * scale)

    # Fill the crown so the canopy closes over the branch tips.
    for _ in range(260):
        a = rng.uniform(0, math.tau)
        b = math.acos(rng.uniform(-0.45, 1.0))
        r = (rng.uniform(0.42, 1.0) ** 0.55) * 2.55 * scale
        scatter(base + Vector((math.sin(b) * math.cos(a) * r,
                               math.sin(b) * math.sin(a) * r,
                               math.cos(b) * r * 0.66 + 3.05 * scale)),
                rng.uniform(0.52, 0.80) * scale)

    make_tube_object(f"{name}_Branches", branch_v, branch_f, MAT_BARK, COL_TREES)
    make_card_object(f"{name}_Canopy", cards, MAT_BLOSSOM_CARD, COL_TREES)


def build_willow_tree(name, location, scale=1.0, seed=0):
    """A waterfront willow: a leaning trunk, arching limbs, hanging strands.

    The drooping strands are drawn as upright cards rather than leaf puffs; the
    card texture already reads as a curtain of leaves at ten metres.
    """
    rng = random.Random(seed)
    base = Vector(location)
    cards = []

    trunk_pts = _polyline(base, Vector((0.0, 0.0, 1.0)), 2.30 * scale, 3, rng, 0.07)
    trunk_v, trunk_f = [], []
    add_tube_geometry(trunk_v, trunk_f, trunk_pts,
                      [0.185 * scale, 0.158 * scale, 0.135 * scale, 0.112 * scale], 7)
    make_tube_object(f"{name}_Trunk", trunk_v, trunk_f, MAT_BARK, COL_TREES)

    branch_v, branch_f = [], []
    for i in range(5):
        angle = math.tau * i / 5 + rng.uniform(-0.30, 0.30)
        heading = Vector((math.cos(angle), math.sin(angle),
                          rng.uniform(0.95, 1.45))).normalized()
        limb = _polyline(_point_on(trunk_pts, rng.uniform(0.58, 0.92)), heading,
                         rng.uniform(1.05, 1.40) * scale, 3, rng, 0.18)
        add_tube_geometry(branch_v, branch_f, limb,
                          [0.082 * scale, 0.068 * scale, 0.052 * scale, 0.036 * scale], 6)

        for j in range(4):
            anchor = _point_on(limb, rng.uniform(0.60, 1.0))
            drop = rng.uniform(2.20, 3.10) * scale
            sway = rng.uniform(-0.35, 0.35) * scale
            strand = [anchor,
                      anchor + Vector((sway * 0.4, sway * 0.4, -drop * 0.45)),
                      anchor + Vector((sway, sway, -drop))]
            add_tube_geometry(branch_v, branch_f, strand,
                              [0.013 * scale, 0.009 * scale, 0.005 * scale], 3)
            for k in range(4):
                point = _point_on(strand, 0.12 + k * 0.24)
                facing = math.atan2(point.y - base.y, point.x - base.x) - math.pi * 0.5
                cards.append((point, rng.uniform(0.95, 1.30) * scale,
                              _card_rotation(rng, upright=True, facing=facing),
                              rng.randrange(4), rng.randrange(4), rng.random() < 0.5))

    make_tube_object(f"{name}_Branches", branch_v, branch_f, MAT_BARK, COL_TREES)
    make_card_object(f"{name}_Canopy", cards, MAT_WILLOW_CARD, COL_TREES)


def build_pine(name, location, height=14.0, seed=0):
    """A low-poly hillside pine.  Read as a silhouette above the far roofs."""
    rng = random.Random(seed)
    base = Vector(location)
    trunk_h = height * 0.34
    add_cylinder(name + "_Trunk", 6, height * 0.018, trunk_h,
                 (base.x, base.y, base.z + trunk_h / 2.0), MAT_TRUNK, COL_TREES)
    for i in range(4):
        radius = height * (0.20 - 0.036 * i) * rng.uniform(0.80, 1.05)
        cone_h = height * 0.30
        z = base.z + height * 0.24 + i * height * 0.155
        ox = rng.uniform(-0.35, 0.35)
        oy = rng.uniform(-0.35, 0.35)
        add_cone(f"{name}_Tier_{i}", 8, radius, radius * 0.10, cone_h,
                 (base.x + ox, base.y + oy, z + cone_h / 2.0),
                 MAT_PINE, COL_TREES)


def build_bamboo(name, location, scale=1.0, seed=0):
    rng = random.Random(seed)
    base = Vector(location)
    for i in range(9):
        angle = rng.uniform(0, math.tau)
        radius = rng.uniform(0.0, 0.8) * scale
        height = rng.uniform(3.6, 5.8) * scale
        x = base.x + math.cos(angle) * radius
        y = base.y + math.sin(angle) * radius
        add_cylinder(f"{name}_Stalk_{i}", 6, 0.035 * scale, height,
                     (x, y, base.z + height / 2.0), MAT_WILLOW, COL_TREES)
        for j in range(2):
            build_shrub(f"{name}_Leaf_{i}_{j}",
                        (x + rng.uniform(-0.35, 0.35) * scale,
                         y + rng.uniform(-0.35, 0.35) * scale,
                         base.z + height * (0.68 + 0.16 * j)),
                        size=1.05 * scale, count=4,
                        seed=SEED + 900 + i * 17 + j, collection=COL_TREES)


# Trees stand on the promenade, not inside the shop volumes: x = ±17.7 leaves
# the canopy free to lean over the water and keeps a walking lane at the shops.
tree_positions = [
    (17.7, -126.0, 1.2), (17.7, -112.0, 1.2), (17.7, -74.0, 1.2),
    (17.7, -50.0, 1.2), (17.7, -8.0, 1.2), (17.7, 54.0, 1.2),
    (17.7, 78.0, 1.2), (17.7, 106.0, 1.2), (17.7, 140.0, 1.2),
    (17.7, 168.0, 1.2),
    (-17.7, -120.0, 1.2), (-17.7, -104.0, 1.2), (-17.7, -88.0, 1.2),
    (-17.7, -56.0, 1.2), (-17.7, -12.0, 1.2), (-17.7, 40.0, 1.2),
    (-17.7, 54.0, 1.2), (-17.7, 110.0, 1.2), (-17.7, 140.0, 1.2),
    (-17.7, 168.0, 1.2),
]
for i, pos in enumerate(tree_positions):
    build_cherry_tree(f"PROP_CherryTree_{i}", pos, scale=random.uniform(1.0, 1.2),
                      seed=SEED + i * 13)

# Willows lean out over the water at the quay edge.
for i, y in enumerate((-108.0, -64.0, 4.0, 72.0, 136.0)):
    for side in (-1, 1):
        build_willow_tree(f"PROP_WillowTree_{'R' if side > 0 else 'L'}_{i}",
                          (side * 14.9, y, GROUND_Z), scale=random.uniform(0.9, 1.2),
                          seed=SEED + 700 + i * 11 + side)

# Hillside pines fill the skyline behind the far roofs.
pine_rng = random.Random(SEED + 505)
for side in (-1, 1):
    for i in range(44):
        x = side * pine_rng.uniform(48.0, 86.0)
        y = pine_rng.uniform(-150.0, 190.0)
        if side > 0 and 20.0 < y < 95.0 and abs(x) < 66.0:
            continue
        build_pine(f"PROP_Pine_{'R' if side > 0 else 'L'}_{i:02d}",
                   (x, y, GROUND_Z), height=pine_rng.uniform(10.0, 20.0),
                   seed=SEED + i * 17 + side)

for i, (x, y) in enumerate(((26.0, 74.0), (-17.0, 44.0), (26.0, -4.0))):
    build_bamboo(f"PROP_Bamboo_{i}", (x, y, GROUND_Z),
                 scale=random.uniform(0.9, 1.15), seed=SEED + 800 + i)

# Drifting petals.
petal_verts = []
petal_faces = []
prng = random.Random(SEED + 202)
for _ in range(380):
    cx = prng.uniform(-40, 40)
    cy = prng.uniform(-90, 170)
    cz = prng.uniform(1.5, 12.0)
    a = prng.uniform(0, math.tau)
    s = prng.uniform(0.06, 0.16)
    dx, dy = math.cos(a) * s, math.sin(a) * s
    base = len(petal_verts)
    petal_verts.extend([
        (cx - dx, cy - dy, cz), (cx + dx, cy - dy, cz + s * 0.4),
        (cx + dx, cy + dy, cz), (cx - dx, cy + dy, cz - s * 0.4),
    ])
    petal_faces.append((base, base + 1, base + 2, base + 3))
petals = add_mesh_object("FX_Petals", petal_verts, petal_faces, MAT_PETAL, COL_FX)
petals.visible_shadow = False

# ---------------------------------------------------------------------------
# Fireworks
# ---------------------------------------------------------------------------

def spark_burst(name, center, radius, material, count=150, seed=0):
    rng = random.Random(seed)
    verts = []
    faces = []
    for i in range(count):
        # Even-ish distribution on a sphere.
        u = rng.uniform(-1, 1)
        theta = rng.uniform(0, math.tau)
        r = radius * (0.72 + rng.uniform(0, 0.28))
        s = math.sqrt(max(0.0, 1 - u * u))
        d = Vector((s * math.cos(theta), s * math.sin(theta), u))
        p = Vector(center) + d * r
        size = rng.uniform(0.35, 0.85)
        base = len(verts)
        # Elongated octahedron along the radial direction.
        verts.extend([
            tuple(p + d * size), tuple(p - d * size),
            tuple(p + Vector((0, 0, size * 0.5))),
            tuple(p - Vector((0, 0, size * 0.5))),
            tuple(p + Vector((size * 0.5, 0, 0))),
            tuple(p - Vector((size * 0.5, 0, 0))),
        ])
        faces.extend([
            (base, base + 2, base + 4), (base, base + 4, base + 3),
            (base, base + 3, base + 5), (base, base + 5, base + 2),
            (base + 1, base + 4, base + 2), (base + 1, base + 3, base + 4),
            (base + 1, base + 5, base + 3), (base + 1, base + 2, base + 5),
        ])
    obj = add_mesh_object(name, verts, faces, material, COL_FX)
    obj.visible_shadow = False
    # Bright core.
    add_sphere(name + "_Core", 1.4, center, emission_material(name + "_CoreMat", "#FFF1C7", 24),
               COL_FX, segments=12, rings=6).visible_shadow = False
    return obj


spark_burst("FX_Firework_Rose", (-120, 80, 90), 22, MAT_FIREWORK_ROSE, count=170, seed=SEED + 1)
spark_burst("FX_Firework_Gold", (125, 155, 100), 18, MAT_FIREWORK_GOLD, count=150, seed=SEED + 2)
spark_burst("FX_Firework_Cyan", (55, 225, 82), 25, MAT_FIREWORK_CYAN, count=190, seed=SEED + 3)

# ---------------------------------------------------------------------------
# Lighting
# ---------------------------------------------------------------------------

world = bpy.data.worlds.new("WORLD_LanternRiver")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (*srgb("#101B3A"), 1.0)
bg.inputs["Strength"].default_value = 0.68

def add_sun(name, from_pos, target, color_hex, energy, angle_deg=2.5):
    data = bpy.data.lights.new(name, "SUN")
    data.energy = energy
    data.color = srgb(color_hex)
    data.angle = math.radians(angle_deg)
    obj = bpy.data.objects.new(name, data)
    COL_LIGHTS.objects.link(obj)
    obj.location = from_pos
    obj.rotation_euler = (Vector(target) - Vector(from_pos)).to_track_quat("-Z", "Y").to_euler()
    return obj


# Two cool moon keys so both river walls and the roof planes read at night.
add_sun("LGT_MoonKey", (220, -120, 260), (0, 40, 0), "#9FC0FF", 3.2)
add_sun("LGT_MoonFill", (-220, -60, 200), (0, 40, 0), "#6F8DD0", 1.4)

# Broad cool fill over the river and a soft top wash for the roof planes.
add_area_light("LGT_RiverFill", (0, -30, 46), (0, 90, 6), "#6F8DD0", 3000, 70)
add_area_light("LGT_RoofWash", (0, 20, 90), (0, 30, 0), "#6F8DD0", 5000, 110)

# Warm street pools.
for side in (-1, 1):
    for i, y in enumerate((-115, -78, -40, 0, 38, 78, 118, 158)):
        add_point_light(f"LGT_Street_{side}_{i}",
                        (side * (RIVER_HALF + 2.6), y, 4.6),
                        "#FFB066", 260.0, 7.0)
    # Facade wash: soft rectangles aimed at the shop fronts.
    for i, y in enumerate((-108, -62, -16, 34, 88, 142)):
        add_area_light(f"LGT_Facade_{side}_{i}",
                       (side * (RIVER_HALF + 3.2), y, 4.6),
                       (side * (RIVER_HALF + PROMENADE), y, 4.6),
                       "#FFB877", 1600, 8)

# Bridge lanterns.
for i, x in enumerate((-13.0, -4.5, 4.5, 13.0)):
    add_point_light(f"LGT_Bridge_{i}", (x, BRIDGE_Y, 7.0), "#FFB36A", 90.0, 2.2)

# Tower glow: warm core at each tier plus a warm rim.
for i, z in enumerate((6.0, 12.0, 18.0, 24.0, 30.0)):
    add_point_light(f"LGT_Tower_{i}", (0, TOWER_Y, z), "#FFB060",
                    280.0 if i == 0 else 180.0, 6.0)
add_area_light("LGT_TowerRim", (0, TOWER_Y - 30, 16), (0, TOWER_Y, 12),
               "#FF7A4A", 500, 16)
# Roof rake light: reads the tile planes and lifted corner tips against the sky.
add_area_light("LGT_TowerRoof", (0, TOWER_Y - 22, 34), (0, TOWER_Y, 24),
               "#FFC58A", 1100, 18)

# Pavilion and plaza.
add_point_light("LGT_Pavilion", (30.5, PAVILION_Y, 6.0), "#FFC070", 200.0, 7.0)

# ---------------------------------------------------------------------------
# Mist planes for depth
# ---------------------------------------------------------------------------

for i, (y, z, w) in enumerate(((55.0, 2.2, 90), (120.0, 3.0, 110), (175.0, 2.6, 90))):
    add_box(f"FX_Mist_{i}", (w, 0.01, 2.2), (0, y, z), MAT_SOFT_MIST, COL_FX)

# ---------------------------------------------------------------------------
# Cameras and render settings
# ---------------------------------------------------------------------------

CAM_HERO = add_camera("CAM_Hero", (0.0, -38.0, 3.2), (0.0, 78.0, 14.0), 45.0)
CAM_BRIDGE = add_camera("CAM_BridgeApproach", (-16.5, -24.0, 4.2), (2.0, 46.0, 9.0), 46.0)
CAM_TOWER = add_camera("CAM_TowerDetail", (12.0, 18.0, 4.2), (0.0, TOWER_Y, 13.5), 40.0)
CAM_STREET = add_camera("CAM_Street", (17.4, -92.0, 4.2), (0.0, 20.0, 8.0), 50.0)
CAM_BOAT = add_camera("CAM_Boat", (2.0, -64.0, 2.6), (7.0, -54.0, 1.8), 42.0)

scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 32 if FAST else 64
scene.eevee.use_raytracing = True
scene.eevee.use_shadows = True
scene.eevee.use_volumetric_shadows = True
scene.eevee.ray_tracing_options.resolution_scale = "1"
scene.eevee.ray_tracing_options.screen_trace_quality = 0.75
scene.eevee.ray_tracing_options.screen_trace_thickness = 0.6
scene.eevee.ray_tracing_options.trace_max_roughness = 0.6
scene.eevee.ray_tracing_options.use_denoise = True
scene.render.resolution_x = 960 if FAST else 1920
scene.render.resolution_y = 540 if FAST else 1080
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX"
scene.view_settings.exposure = 0.55
try:
    scene.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass

# Compositor bloom: Blender 5.3 compositor is a node group.
comp = bpy.data.node_groups.new("COMP_LanternRiver", "CompositorNodeTree")
scene.compositing_node_group = comp
comp.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
rl = comp.nodes.new("CompositorNodeRLayers")
glare = comp.nodes.new("CompositorNodeGlare")
glare.inputs["Type"].default_value = "Bloom"
glare.inputs["Quality"].default_value = "High"
glare.inputs["Threshold"].default_value = 1.3
glare.inputs["Size"].default_value = 5
out = comp.nodes.new("NodeGroupOutput")
comp.links.new(rl.outputs["Image"], glare.inputs["Image"])
comp.links.new(glare.outputs["Image"], out.inputs[0])
scene.render.use_compositing = True

# Light probes (best effort; EEVEE ignores unsupported setups gracefully).
try:
    bpy.ops.object.lightprobe_add(type="PLANE", location=(0, 20, 0.1))
    probe = bpy.context.object
    probe.name = "PRB_WaterReflection"
    probe.scale = (RIVER_HALF, 170.0, 1.0)
    move_to_collection(probe, COL_ENV)
except Exception as exc:
    print("Lightprobe skipped:", exc)

# ---------------------------------------------------------------------------
# Save scene and render previews
# ---------------------------------------------------------------------------

scene.camera = CAM_HERO
SCENE_BLEND = os.path.join(EXPORT_DIR, "SM_Scene_LanternRiver_Night.blend")
bpy.ops.wm.save_as_mainfile(filepath=SCENE_BLEND)

def render_camera(cam, filename):
    scene.camera = cam
    scene.render.filepath = os.path.join(RENDER_DIR, filename)
    if SKIP_RENDER:
        return scene.render.filepath
    bpy.ops.render.render(write_still=True)
    return scene.render.filepath

shots = [
    (CAM_HERO, "01_hero.png"),
    (CAM_BRIDGE, "02_bridge_approach.png"),
    (CAM_TOWER, "03_tower_detail.png"),
    (CAM_STREET, "04_street.png"),
    (CAM_BOAT, "05_boat.png"),
]
for cam, filename in shots:
    print("RENDER", filename)
    render_camera(cam, filename)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

tris = 0
mesh_objects = 0
for obj in bpy.data.objects:
    if obj.type == "MESH" and not obj.hide_render:
        mesh_objects += 1
        obj.data.calc_loop_triangles()
        tris += len(obj.data.loop_triangles)
report = {
    "scene": "SM_Scene_LanternRiver_Night",
    "blend": SCENE_BLEND,
    "mesh_objects": mesh_objects,
    "triangles": tris,
    "materials": len([m for m in bpy.data.materials if m.users > 0]),
    "lights": len([o for o in bpy.data.objects if o.type == "LIGHT"]),
    "cameras": [o.name for o in bpy.data.objects if o.type == "CAMERA"],
    "shots": [f for _, f in shots],
    "kit_pieces": [o.name for o in bpy.data.objects
                   if o.name.startswith(("BLD_", "LM_", "PROP_Stall"))][:60],
}
with open(os.path.join(REPORT_DIR, "scene_report.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2, ensure_ascii=False)
print("SCENE_REPORT", json.dumps(report, indent=2))
