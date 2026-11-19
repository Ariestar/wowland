"""Render the foliage card atlases used by the lantern-river trees.

The reference world builds its canopies from thousands of instanced cards
rather than solid puffs: the silhouette comes from the card texture, not the
mesh.  These atlases are rendered from real 3D blossom clusters and willow
strands, so the cards carry baked form and occlusion instead of flat paint.

Four variants fill a 2 x 2 grid in one 2048 px RGBA image.  Each render writes
the full atlas canvas with the camera shifted into one quadrant, which keeps
the tiles pixel-exact and avoids a colour round-trip through a compositor.

    blender -b --python scripts/make_foliage_atlas.py            # both atlases
    blender -b --python scripts/make_foliage_atlas.py -- willow  # just one
"""

import math
import os
import random
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "textures")
TILE = 1024
ATLAS = TILE * 2
VARIANTS = 4
SAMPLES = 64


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------

def srgb(hex_value):
    hex_value = hex_value.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(hex_value[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def make_mesh(name, verts, faces, mats, collection, tints=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    for mat in mats:
        obj.data.materials.append(mat)
    if tints is not None:
        layer = mesh.color_attributes.new(name="Tint", type="FLOAT_COLOR",
                                          domain="POINT")
        for i, tint in enumerate(tints):
            layer.data[i].color = (tint[0], tint[1], tint[2], 1.0)
    return obj


def tube(points, radii, sides=5):
    """A tapered tube along a polyline, with parallel-transported frames."""
    verts = []
    faces = []
    count = len(points)
    tangents = []
    for i in range(count):
        a = points[max(0, i - 1)]
        b = points[min(count - 1, i + 1)]
        tangents.append((b - a).normalized())

    normal = tangents[0].orthogonal().normalized()
    frames = []
    for i in range(count):
        if i:
            prev = tangents[i - 1]
            cur = tangents[i]
            quat = prev.rotation_difference(cur)
            normal = (quat @ normal).normalized()
            normal = (normal - cur * normal.dot(cur)).normalized()
        frames.append(normal)

    for i in range(count):
        t = tangents[i]
        n = frames[i]
        b = t.cross(n)
        r = radii[i]
        for j in range(sides):
            a = math.tau * j / sides
            verts.append(tuple(points[i] + n * (math.cos(a) * r) + b * (math.sin(a) * r)))

    for i in range(count - 1):
        for j in range(sides):
            a = i * sides + j
            b = i * sides + (j + 1) % sides
            faces.append((a, b, b + sides, a + sides))

    # Caps keep the silhouette closed against the transparent film.
    tip = len(verts)
    verts.append(tuple(points[-1]))
    for j in range(sides):
        a = (count - 1) * sides + j
        faces.append((a, (count - 1) * sides + (j + 1) % sides, tip))
    return verts, faces


def petal(length, width, cup, curl, rows=7, cols=6):
    """A cupped petal growing along +Y from the origin."""
    verts = []
    for i in range(rows):
        t = i / (rows - 1)
        profile = max(0.05, math.sin(math.pi * (t ** 1.15)) ** 0.7)
        w = width * profile
        for j in range(cols):
            s = (j / (cols - 1)) * 2.0 - 1.0
            x = s * w
            y = t * length
            z = cup * (s * s) * (1.0 - 0.3 * t) + curl * (t ** 2.0) * length
            verts.append((x, y, z))
    faces = []
    for i in range(rows - 1):
        for j in range(cols - 1):
            a = i * cols + j
            faces.append((a, a + 1, a + cols + 1, a + cols))
    return verts, faces


def add_parts(dst_v, dst_f, src_v, src_f, matrix):
    offset = len(dst_v)
    for v in src_v:
        dst_v.append(tuple(matrix @ Vector(v)))
    for f in src_f:
        dst_f.append(tuple(i + offset for i in f))


# ---------------------------------------------------------------------------
# Blossom cluster
# ---------------------------------------------------------------------------

def blossom_cluster(rng):
    """One 0.5 m clump of five-petal blossoms on a twig."""
    verts = []
    faces = []
    petal_mats = []
    tints = []

    size = rng.uniform(0.040, 0.052)
    length = size * rng.uniform(0.95, 1.1)
    tilt = math.radians(rng.uniform(26, 36))

    flower_v = []
    flower_f = []
    for k in range(5):
        pv, pf = petal(length, size * 0.46, size * 0.30, size * 0.24)
        m = (Matrix.Rotation(math.tau * k / 5 + rng.uniform(-0.08, 0.08), 4, "Z")
             @ Matrix.Rotation(-tilt, 4, "X"))
        add_parts(flower_v, flower_f, pv, pf, m)
    # Warm heart.
    heart_v, heart_f = [], []
    add_parts(heart_v, heart_f, *tube(
        [Vector((0, 0, 0)), Vector((0, 0, size * 0.16))],
        [size * 0.16, size * 0.10], sides=6), Matrix.Identity(4))

    radius = 0.245
    lumps = [(rng.uniform(0, math.tau), rng.uniform(0, math.pi),
              rng.uniform(0.30, 0.52)) for _ in range(5)]

    def place(n, r, tint):
        pos = n * r
        jitter = Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4),
                         rng.uniform(-0.4, 0.4)))
        facing = (n + jitter).normalized()
        quat = facing.to_track_quat("Z", "Y").to_matrix().to_4x4()
        quat = quat @ Matrix.Rotation(rng.uniform(0, math.tau), 4, "Z")
        m = Matrix.Translation(pos) @ quat @ Matrix.Scale(rng.uniform(0.85, 1.15), 4)
        before = len(verts)
        add_parts(verts, faces, flower_v, flower_f, m)
        petal_mats.extend([0] * len(flower_f))
        add_parts(verts, faces, heart_v, heart_f, m)
        petal_mats.extend([1] * len(heart_f))
        tints.extend([tint] * (len(verts) - before))

    count = 104
    for i in range(count):
        # Fibonacci shell keeps the clump even instead of leaving bald patches.
        u = (i + 0.5) / count
        theta = math.acos(1.0 - 2.0 * u)
        phi = math.tau * i * 0.6180339887
        n = Vector((math.sin(theta) * math.cos(phi),
                    math.sin(theta) * math.sin(phi),
                    math.cos(theta)))
        r = radius * rng.uniform(0.55, 1.0)
        for la, lp, lw in lumps:
            axis = Vector((math.sin(lp) * math.cos(la), math.sin(lp) * math.sin(la),
                           math.cos(lp)))
            r += lw * 0.16 * max(0.0, n.dot(axis)) ** 3

        # Most blossoms sit near the white end; a quarter carry the deeper rose
        # that gives a canopy depth when hundreds of cards overlap.
        if rng.random() < 0.26:
            tint = (rng.uniform(0.72, 0.86), rng.uniform(0.42, 0.56),
                    rng.uniform(0.52, 0.66))
        elif rng.random() < 0.5:
            tint = (rng.uniform(1.0, 1.12), rng.uniform(0.92, 1.02),
                    rng.uniform(0.95, 1.05))
        else:
            tint = (rng.uniform(0.88, 1.0), rng.uniform(0.72, 0.86),
                    rng.uniform(0.80, 0.92))
        place(n, r, tint)

    # A ragged outer fringe stops the card reading as a ball of flowers when
    # dozens of them overlap in the canopy.
    for _ in range(14):
        a = rng.uniform(0, math.tau)
        b = math.acos(rng.uniform(-0.75, 0.9))
        n = Vector((math.sin(b) * math.cos(a), math.sin(b) * math.sin(a), math.cos(b)))
        place(n, radius * rng.uniform(1.05, 1.34),
              (rng.uniform(0.9, 1.1), rng.uniform(0.7, 0.95), rng.uniform(0.8, 1.0)))

    # Twigs give the clump something to hang from.
    for _ in range(3):
        start = Vector((rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05),
                        rng.uniform(-0.05, 0.05)))
        end = Vector((rng.uniform(-0.26, 0.26), rng.uniform(-0.26, 0.26),
                      rng.uniform(-0.24, 0.24)))
        mid = (start + end) * 0.5 + Vector((rng.uniform(-0.05, 0.05),
                                            rng.uniform(-0.05, 0.05),
                                            rng.uniform(-0.05, 0.05)))
        tv, tf = tube([start, mid, end], [0.007, 0.005, 0.003], sides=4)
        add_parts(verts, faces, tv, tf, Matrix.Identity(4))
        petal_mats.extend([2] * len(tf))
        tints.extend([(1.0, 1.0, 1.0)] * len(tf))

    return verts, faces, petal_mats, tints


# ---------------------------------------------------------------------------
# Willow strand
# ---------------------------------------------------------------------------

def shrub_clump(rng):
    """A rounded leafy clump, for potted plants and low hedges."""
    verts = []
    faces = []
    mats = []
    tints = []

    leaf_v, leaf_f = petal(0.105, 0.048, 0.020, 0.006, rows=5, cols=4)
    radius = 0.235
    lumps = [(rng.uniform(0, math.tau), rng.uniform(0, math.pi),
              rng.uniform(0.25, 0.5)) for _ in range(4)]

    count = 150
    for i in range(count):
        u = (i + 0.5) / count
        theta = math.acos(1.0 - 2.0 * u)
        phi = math.tau * i * 0.6180339887
        n = Vector((math.sin(theta) * math.cos(phi),
                    math.sin(theta) * math.sin(phi),
                    math.cos(theta)))
        r = radius * rng.uniform(0.45, 1.0)
        for la, lp, lw in lumps:
            axis = Vector((math.sin(lp) * math.cos(la), math.sin(lp) * math.sin(la),
                           math.cos(lp)))
            r += lw * 0.18 * max(0.0, n.dot(axis)) ** 3

        pos = n * r
        facing = (n + Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5),
                              rng.uniform(-0.5, 0.5)))).normalized()
        quat = facing.to_track_quat("Z", "Y").to_matrix().to_4x4()
        quat = quat @ Matrix.Rotation(rng.uniform(0, math.tau), 4, "Z")
        # Leaves grow out of the stem, so tilt them away from the surface
        # normal instead of laying them flat on it.
        quat = quat @ Matrix.Rotation(math.radians(rng.uniform(35, 80)), 4, "X")
        m = Matrix.Translation(pos) @ quat @ Matrix.Scale(rng.uniform(0.75, 1.2), 4)
        before = len(verts)
        add_parts(verts, faces, leaf_v, leaf_f, m)
        mats.extend([0] * len(leaf_f))
        v = rng.uniform(0.72, 1.18)
        tints.extend([(v * 0.94, v, v * 0.82)] * (len(verts) - before))

    # A few woody stems break the silhouette at the base.
    for _ in range(3):
        start = Vector((rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03), -0.1))
        end = Vector((rng.uniform(-0.14, 0.14), rng.uniform(-0.14, 0.14),
                      rng.uniform(-0.02, 0.12)))
        tv, tf = tube([start, (start + end) * 0.5, end], [0.010, 0.007, 0.004], sides=4)
        add_parts(verts, faces, tv, tf, Matrix.Identity(4))
        mats.extend([2] * len(tf))
        tints.extend([(1.0, 1.0, 1.0)] * len(tf))

    return verts, faces, mats, tints


def willow_strand(rng):
    """Three drooping willow branches, dense enough to tile as one card."""
    verts = []
    faces = []
    mats = []
    tints = []

    leaf_v, leaf_f = petal(0.205, 0.017, 0.005, -0.016, rows=5, cols=4)

    for strand in range(3):
        length = rng.uniform(1.05, 1.25)
        ox = (strand - 1) * 0.13 + rng.uniform(-0.03, 0.03)
        lean = Vector((rng.uniform(-0.14, 0.14), rng.uniform(-0.16, 0.16), 0.0))
        points = []
        for i in range(7):
            t = i / 6.0
            points.append(Vector((ox + lean.x * t * t, lean.y * t * t,
                                  0.46 - length * t)))
        tv, tf = tube(points, [0.007, 0.006, 0.005, 0.0045, 0.004, 0.0035, 0.0025],
                      sides=4)
        add_parts(verts, faces, tv, tf, Matrix.Identity(4))
        mats.extend([2] * len(tf))
        tints.extend([(1.0, 1.0, 1.0)] * len(tf))

        leaves = 88
        for i in range(leaves):
            t = 0.02 + 0.96 * (i / (leaves - 1.0))
            idx = t * 6.0
            i0 = min(5, int(idx))
            f = idx - i0
            base = points[i0].lerp(points[i0 + 1], f)
            side = 1 if i % 2 else -1
            ang = rng.uniform(0.25, 1.35) * side + math.tau * (i % 3) / 3.0
            # Leaves hang: the petal grows along +Y, so a rotation past 180 deg
            # turns it downward instead of up.
            droop = math.radians(rng.uniform(198, 252))
            m = (Matrix.Translation(base + Vector((0, 0, -0.012)))
                 @ Matrix.Rotation(ang, 4, "Z")
                 @ Matrix.Rotation(droop, 4, "X")
                 @ Matrix.Scale(rng.uniform(0.8, 1.25), 4))
            before = len(verts)
            add_parts(verts, faces, leaf_v, leaf_f, m)
            mats.extend([0] * len(leaf_f))
            v = rng.uniform(0.76, 1.16)
            tints.extend([(v * 0.94, v, v * 0.84)] * (len(verts) - before))

    return verts, faces, mats, tints


# ---------------------------------------------------------------------------
# Scene assembly
# ---------------------------------------------------------------------------

def material(name, color, roughness, emission=None, strength=0.0, tint=False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*srgb(color), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*srgb(emission), 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    if tint:
        attr = nt.nodes.new("ShaderNodeVertexColor")
        attr.layer_name = "Tint"
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 1.0
        mix.inputs["Color1"].default_value = (*srgb(color), 1.0)
        nt.links.new(attr.outputs["Color"], mix.inputs["Color2"])
        nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def build_scene(kind, seed):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.render.film_transparent = True
    scene.render.resolution_x = ATLAS
    scene.render.resolution_y = ATLAS
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 15
    # Standard view transform keeps the authored albedo; AgX would desaturate
    # the blossoms into grey.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0

    world = bpy.data.worlds.new("AtlasWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.62, 0.66, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.85
    scene.world = world

    rng = random.Random(seed)
    collection = bpy.data.collections.new("Atlas")
    scene.collection.children.link(collection)

    if kind == "blossom":
        mats = [
            material("Petal", "#FBD3E2", 0.62, tint=True),
            material("Heart", "#F5C86A", 0.55),
            material("Twig", "#4A2A22", 0.85),
        ]
        verts, faces, slots, tints = blossom_cluster(rng)
    elif kind == "shrub":
        mats = [
            material("Leaf", "#8FB25E", 0.66, tint=True),
            material("LeafB", "#8FB25E", 0.66, tint=True),
            material("Stem", "#4B3A22", 0.85),
        ]
        verts, faces, slots, tints = shrub_clump(rng)
    else:
        mats = [
            material("Leaf", "#A6C486", 0.66, tint=True),
            material("LeafB", "#A6C486", 0.66, tint=True),
            material("Stem", "#4B3A22", 0.85),
        ]
        verts, faces, slots, tints = willow_strand(rng)

    obj = make_mesh(f"Atlas_{kind}", verts, faces, mats, collection, tints)
    for poly, slot in zip(obj.data.polygons, slots):
        poly.material_index = slot
        poly.use_smooth = True

    # Soft key from the upper left plus a cool fill keeps the form readable
    # without baking a hard shadow direction into the card.
    key_data = bpy.data.lights.new("Key", type="SUN")
    key_data.energy = 2.4
    key_data.angle = math.radians(24)
    key = bpy.data.objects.new("Key", key_data)
    key.rotation_euler = (math.radians(58), 0, math.radians(-38))
    collection.objects.link(key)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0, -3.0, 0)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    collection.objects.link(cam)
    scene.camera = cam

    return scene, cam, obj


def frame_camera(cam, obj, quadrant, padding=1.10):
    """Aim the camera so the subject fills one quadrant of the full atlas."""
    coords = [obj.matrix_world @ Vector(v.co) for v in obj.data.vertices]
    xs = [c.x for c in coords]
    zs = [c.z for c in coords]
    span_x = max(xs) - min(xs)
    span_z = max(zs) - min(zs)
    cx = (max(xs) + min(xs)) * 0.5
    cz = (max(zs) + min(zs)) * 0.5
    # ortho_scale spans the whole atlas, so the subject covers half of it.
    cam.data.ortho_scale = max(span_x, span_z) * padding * 2.0
    cam.location = (cx, -3.0, cz)
    col = quadrant % 2
    row = quadrant // 2
    # A positive shift moves the frame right/up, which slides the subject
    # left/down in the image.
    cam.data.shift_x = 0.25 if col == 0 else -0.25
    cam.data.shift_y = 0.25 if row == 0 else -0.25


def render_atlas(kind, out_dir):
    out_path = os.path.join(out_dir, f"{kind}_atlas.png")
    tiles = []
    for index in range(VARIANTS):
        scene, cam, obj = build_scene(kind, seed=900 + index * 37)
        # Rotate the subject instead of the camera so the light direction stays
        # consistent between tiles.
        obj.rotation_euler = (0, 0, math.tau * index / VARIANTS + 0.35)
        bpy.context.view_layer.update()
        frame_camera(cam, obj, index)
        tile = os.path.join(out_dir, f"_tile_{kind}_{index}.png")
        scene.render.filepath = tile
        bpy.ops.render.render(write_still=True)
        tiles.append(tile)
        print("FOLIAGE_TILE", kind, index, tile)

    # Each tile is a full atlas canvas with the subject in one quadrant, so a
    # per-channel maximum merges them without touching the empty regions.
    merged = None
    for tile in tiles:
        image = bpy.data.images.load(tile, check_existing=False)
        width, height = image.size
        buf = np.array(image.pixels[:], dtype=np.float32).reshape(height, width, 4)
        merged = buf.copy() if merged is None else np.maximum(merged, buf)
        bpy.data.images.remove(image)
        os.remove(tile)

    out = bpy.data.images.new(f"{kind}_atlas", width=ATLAS, height=ATLAS, alpha=True)
    out.pixels = merged.ravel().tolist()
    out.filepath_raw = out_path
    out.file_format = "PNG"
    out.save()
    return out_path


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    kinds = argv if argv else ["blossom", "willow", "shrub"]
    os.makedirs(OUT_DIR, exist_ok=True)
    for kind in kinds:
        print("FOLIAGE_ATLAS", render_atlas(kind, OUT_DIR))


main()
