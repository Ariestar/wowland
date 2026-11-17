"""Shangyuan Lantern Night - self-contained, repeatable Blender asset builder.

Run with Blender 5.2:
  blender -b --python sy_build.py -- --greybox
  blender -b --python sy_build.py -- --full

Only collections prefixed SYR_/SY_ are replaced. No little-world code is imported.
"""
import argparse
import json
import math
import os
import random
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Euler, Matrix, Vector

ROOT = Path(__file__).resolve().parents[3]
BLEND_PATH = ROOT / "assets/blender/shangyuan-lantern-night.blend"
ARTIFACTS = ROOT / "artifacts/shangyuan"
SCENE_NAME = "SY_Sh angyuan".replace(" ", "")
RESOURCE_PREFIX = "SYR_"
TAU = math.tau

RESOURCE_IDS = [
    "model-riverbanks", "model-paifang", "model-bridge", "model-lantern-tower",
    *[f"model-shop-{i:02d}" for i in range(1, 7)],
    "model-stall-riddle", "model-stall-tea",
    *[f"model-lantern-array-s{i}" for i in range(1, 5)],
    "model-river-lantern-lotus", "model-river-lantern-paperboat", "model-river-lantern-fish",
    "model-boat", "model-skiff", "model-performance", "model-quay", "model-water",
]
ORIGINS = {
    "model-riverbanks": (90, 0, 0), "model-paifang": (20, 18, 0.58),
    "model-bridge": (90, 0, 0), "model-lantern-tower": (98, 23, 0.58),
    "model-shop-01": (34, 25, 0.58), "model-shop-02": (48, 25, 0.58),
    "model-shop-03": (62, 25, 0.58), "model-shop-04": (76, 25, 0.58),
    "model-shop-05": (114, 25, 0.58), "model-shop-06": (151, 26, 0.58),
    "model-stall-riddle": (67, 13.8, 0.58), "model-stall-tea": (133, 25, 0.58),
    "model-lantern-array-s1": (38, 0, 0), "model-lantern-array-s2": (72, 0, 0),
    "model-lantern-array-s3": (128, 0, 0), "model-lantern-array-s4": (162, 0, 0),
    "model-river-lantern-lotus": (121, -2, 0.06),
    "model-river-lantern-paperboat": (126, 2, 0.06),
    "model-river-lantern-fish": (132, -3, 0.06),
    "model-boat": (55, -4, 0.03), "model-skiff": (154, 4, 0.03),
    "model-performance": (140, -21, 0.58), "model-quay": (125, 8.5, 0),
    "model-water": (90, 0, 0),
}


def linear(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def color(hex_value):
    h = hex_value.lstrip("#")
    return tuple(linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))


def material(name, hex_value, roughness=0.8, metallic=0.0, emission=None, strength=0.0, alpha=1.0):
    m = bpy.data.materials.new("SY_" + name)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*color(hex_value), alpha)
    p.inputs["Roughness"].default_value = roughness
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Alpha"].default_value = alpha
    if emission:
        p.inputs["Emission Color"].default_value = (*color(emission), 1)
        p.inputs["Emission Strength"].default_value = strength
    m.diffuse_color = (*color(hex_value), alpha)
    if alpha < 1:
        m.surface_render_method = "DITHERED"
    return m


def palette():
    # Exactly twelve shared materials; all are realtime PBR, with optional emission.
    return {
        "stone": material("Stone", "747984", 0.9),
        "plaster": material("Plaster", "A89E89", 0.95),
        "wood": material("Wood", "865137", 0.78),
        "dark": material("DarkWood", "382A2B", 0.74),
        "roof": material("Roof", "496A7E", 0.66, 0.12),
        "red": material("Vermilion", "A33B30", 0.7),
        "gold": material("Gold", "D1A255", 0.4, 0.5),
        "paper": material("Paper", "E2B573", 0.72, emission="FFAD4A", strength=0.75),
        "lantern": material("Lantern", "FFD18A", 0.48, emission="FF9E3D", strength=3.4),
        "water": material("Water", "102D42", 0.16, 0.52),
        "foliage": material("Foliage", "314C48", 0.96),
        "reflection": material("Reflection", "E6B469", 0.5, emission="FFB65A", strength=1.15, alpha=0.2),
    }


class Builder:
    """Small geometry builder that merges parts while retaining shared material slots."""
    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    def merge(self, tmp, mat, matrix=None):
        if matrix is not None:
            bmesh.ops.transform(tmp, matrix=matrix, verts=tmp.verts)
        mesh = bpy.data.meshes.new("_sy_tmp")
        tmp.to_mesh(mesh)
        tmp.free()
        if mat not in self.mats:
            self.mats.append(mat)
        index = self.mats.index(mat)
        before = len(self.bm.faces)
        self.bm.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)
        self.bm.faces.ensure_lookup_table()
        for face in self.bm.faces[before:]:
            face.material_index = index

    @staticmethod
    def matrix(loc, rot=(0, 0, 0)):
        return Matrix.Translation(Vector(loc)) @ Euler(rot).to_matrix().to_4x4()

    def box(self, mat, size, loc, rot=(0, 0, 0), bevel=0.015):
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1)
        bmesh.ops.scale(tmp, vec=Vector(size), verts=tmp.verts)
        if bevel:
            bmesh.ops.bevel(tmp, geom=list(tmp.edges), offset=min(bevel, min(size) * 0.3),
                            segments=1, affect="EDGES", clamp_overlap=True)
        self.merge(tmp, mat, self.matrix(loc, rot))

    def cyl(self, mat, radius, depth, loc, rot=(0, 0, 0), vertices=12, radius2=None):
        tmp = bmesh.new()
        bmesh.ops.create_cone(tmp, cap_ends=True, segments=vertices, radius1=radius,
                              radius2=radius if radius2 is None else radius2, depth=depth)
        for face in tmp.faces:
            face.smooth = len(face.verts) == 4
        self.merge(tmp, mat, self.matrix(loc, rot))

    def beam(self, mat, a, b, radius=0.04, vertices=8):
        a, b = Vector(a), Vector(b)
        delta = b - a
        if delta.length < 0.0001:
            return
        rot = delta.to_track_quat("Z", "Y").to_euler()
        self.cyl(mat, radius, delta.length, (a + b) / 2, rot, vertices)

    def blob(self, mat, radius, loc, scale=(1, 1, 1), subdivisions=1):
        tmp = bmesh.new()
        bmesh.ops.create_icosphere(tmp, subdivisions=subdivisions, radius=radius)
        bmesh.ops.scale(tmp, vec=Vector(scale), verts=tmp.verts)
        for face in tmp.faces:
            face.smooth = True
        self.merge(tmp, mat, Matrix.Translation(Vector(loc)))

    def torus(self, mat, major, minor, loc, rot=(0, 0, 0), segments=20, sides=6):
        tmp = bmesh.new()
        rings = []
        for i in range(segments):
            a = TAU * i / segments
            ring = []
            for j in range(sides):
                t = TAU * j / sides
                ring.append(tmp.verts.new(((major + minor * math.cos(t)) * math.cos(a),
                                           (major + minor * math.cos(t)) * math.sin(a),
                                           minor * math.sin(t))))
            rings.append(ring)
        for i in range(segments):
            for j in range(sides):
                tmp.faces.new((rings[i][j], rings[i][(j + 1) % sides],
                               rings[(i + 1) % segments][(j + 1) % sides], rings[(i + 1) % segments][j]))
        self.merge(tmp, mat, self.matrix(loc, rot))

    def poly(self, mat, vertices, faces, loc=(0, 0, 0), rot=(0, 0, 0), up=False):
        tmp = bmesh.new()
        verts = [tmp.verts.new(v) for v in vertices]
        for face in faces:
            tmp.faces.new([verts[i] for i in face])
        bmesh.ops.recalc_face_normals(tmp, faces=list(tmp.faces))
        if up:
            tmp.normal_update()
            flipped = [face for face in tmp.faces if face.normal.z < 0]
            if flipped:
                bmesh.ops.reverse_faces(tmp, faces=flipped)
        self.merge(tmp, mat, self.matrix(loc, rot))

    def build(self, resource_id, collection, location, rot_z=0):
        bmesh.ops.recalc_face_normals(self.bm, faces=list(self.bm.faces))
        mesh = bpy.data.meshes.new(resource_id)
        self.bm.to_mesh(mesh)
        self.bm.free()
        for mat in self.mats:
            mesh.materials.append(mat)
        obj = bpy.data.objects.new(resource_id, mesh)
        collection.objects.link(obj)
        obj.location = location
        obj.rotation_euler.z = rot_z
        obj["resource_id"] = resource_id
        obj["units"] = "meters"
        obj.matrix_world = Matrix.Translation(Vector(location)) @ Matrix.Rotation(rot_z, 4, "Z")
        return obj


def own_scene():
    scene = bpy.data.scenes.get(SCENE_NAME)
    if scene is None:
        scene = bpy.data.scenes.new(SCENE_NAME)
    bpy.context.window.scene = scene
    return scene


def clean_owned(scene):
    for collection in list(scene.collection.children):
        if collection.name.startswith("SYR_") or collection.name in {"SY_Assets", "SY_Environment"}:
            for obj in list(collection.all_objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            def remove_tree(c):
                for child in list(c.children):
                    remove_tree(child)
                bpy.data.collections.remove(c)
            remove_tree(collection)
    for mat in list(bpy.data.materials):
        if mat.name.startswith("SY_") and mat.users == 0:
            bpy.data.materials.remove(mat)


def collection(scene, resource_id):
    c = bpy.data.collections.new(RESOURCE_PREFIX + resource_id)
    scene.collection.children.link(c)
    c["resource_id"] = resource_id
    c["origin"] = ORIGINS[resource_id]
    return c


def build_resource(scene, resource_id, builder, rot_z=0):
    return builder.build(resource_id, collection(scene, resource_id), ORIGINS[resource_id], rot_z)


def add_label(root, text, loc, size=0.45, rotation=(math.pi / 2, 0, 0), font=None, mat=None):
    if font is None:
        return None
    try:
        curve = bpy.data.curves.new("Sign_" + text, "FONT")
        curve.body = text
        curve.font = font
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        curve.size = size
        curve.resolution_u = 3
        curve.extrude = 0.002
        curve.materials.append(mat)
        obj = bpy.data.objects.new("Sign_" + text, curve)
        root.users_collection[0].objects.link(obj)
        obj.parent = root
        obj.location = loc
        obj.rotation_euler = rotation
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.convert(target="MESH")
        return bpy.context.object
    except Exception as exc:
        print("SY_FONT_LABEL_WARNING", text, repr(exc))
        return None


def lantern(b, p, loc, radius=0.28, height=0.65):
    x, y, z = loc
    # Eight-sided paper shades and square ribs survive at game distance without hidden subdivision.
    b.cyl(p["lantern"], radius, height, loc, vertices=8, radius2=radius * 0.88)
    for dz in (-height / 2, height / 2):
        b.cyl(p["gold"], radius * 1.04, 0.05, (x, y, z + dz), vertices=8)
    for a in (0, math.pi / 2, math.pi, math.pi * 1.5):
        b.box(p["red"], (0.024, 0.024, height * 0.86),
              (x + math.cos(a) * radius * 0.93, y + math.sin(a) * radius * 0.93, z), bevel=0)
    b.beam(p["red"], (x, y, z - height / 2 - 0.03), (x, y, z - height / 2 - 0.28), 0.014, 6)


def lattice(b, p, center, width, height, side=False):
    x, y, z = center
    panel_size = (0.07, width, height) if side else (width, 0.07, height)
    b.box(p["paper"], panel_size, center, bevel=0)
    for i in range(5):
        u = -width / 2 + width * i / 4
        size = (0.09, 0.055, height + 0.12) if side else (0.055, 0.09, height + 0.12)
        pos = (x, y + u, z) if side else (x + u, y, z)
        b.box(p["dark"], size, pos, bevel=0)
    for i in range(4):
        zz = z - height / 2 + height * i / 3
        size = (0.09, width + 0.12, 0.055) if side else (width + 0.12, 0.09, 0.055)
        b.box(p["dark"], size, (x, y, zz), bevel=0)


def festoon(b, p, a, bb, count=7, sag=0.75, lantern_radius=0.2, drop=0.42):
    """A sagging cable with individually dropped lanterns, not a rigid light bar."""
    a, bb = Vector(a), Vector(bb)
    points = []
    for i in range(25):
        t = i / 24
        v = a.lerp(bb, t)
        v.z -= sag * 4 * t * (1 - t)
        points.append(v)
    for p0, p1 in zip(points, points[1:]):
        b.beam(p["dark"], p0, p1, 0.018, 6)
    for i in range(count):
        t = (i + 0.5) / count
        v = a.lerp(bb, t)
        v.z -= sag * 4 * t * (1 - t)
        extra = drop + 0.12 * (i % 3)
        b.beam(p["dark"], v, v - Vector((0, 0, extra)), 0.012, 6)
        lantern(b, p, v - Vector((0, 0, extra + lantern_radius * 1.15)), lantern_radius, lantern_radius * 2.25)


def banner(b, p, loc, width=0.65, height=1.8, facing="front", mat=None):
    """Cloth festival banner with a pole, gold hem and a forked lower edge."""
    x, y, z = loc
    mat = mat or p["red"]
    if facing == "front":
        b.beam(p["gold"], (x - width * 0.65, y, z + height / 2 + 0.12),
               (x + width * 0.65, y, z + height / 2 + 0.12), 0.025, 8)
        verts = [(x - width / 2, y, z + height / 2), (x + width / 2, y, z + height / 2),
                 (x + width / 2, y + 0.06, z - height / 2 + 0.18), (x, y + 0.09, z - height / 2),
                 (x - width / 2, y + 0.06, z - height / 2 + 0.18)]
        b.poly(mat, verts, [(0, 1, 2, 3, 4)])
        for xx in (x - width * 0.38, x + width * 0.38):
            b.beam(p["gold"], (xx, y - 0.015, z + height * 0.38), (xx, y - 0.015, z - height * 0.25), 0.015, 6)
    else:
        b.beam(p["gold"], (x, y - width * 0.65, z + height / 2 + 0.12),
               (x, y + width * 0.65, z + height / 2 + 0.12), 0.025, 8)
        verts = [(x, y - width / 2, z + height / 2), (x, y + width / 2, z + height / 2),
                 (x + 0.06, y + width / 2, z - height / 2 + 0.18), (x + 0.09, y, z - height / 2),
                 (x + 0.06, y - width / 2, z - height / 2 + 0.18)]
        b.poly(mat, verts, [(0, 1, 2, 3, 4)])


def mini_lotus(b, p, loc, scale=1.0, angle=0):
    """Static environmental lotus; the interactive prototype remains a separate resource."""
    x, y, z = loc
    for i in range(6):
        a = TAU * i / 6 + angle
        r = 0.28 * scale
        verts = [(0, 0, 0.035 * scale), (r * 0.55, -0.10 * scale, 0.08 * scale),
                 (r, 0, 0.17 * scale), (r * 0.55, 0.10 * scale, 0.08 * scale)]
        b.poly(p["red"] if i % 2 else p["paper"], verts, [(0, 1, 2, 3)], (x, y, z), (0, 0, a))
    b.cyl(p["lantern"], 0.095 * scale, 0.22 * scale, (x, y, z + 0.17 * scale), vertices=8)


def gable_roof(b, p, width, depth, z, rise=1.35, center=(0, 0), corner=0.32):
    cx, cy = center
    hw, hd = width / 2, depth / 2
    nx, nv = 8, 5
    for sign in (-1, 1):
        verts = []
        for j in range(nv + 1):
            v = j / nv
            for i in range(nx + 1):
                u = -1 + 2 * i / nx
                x = cx + hw * u
                y = cy + sign * hd * (1 - v)
                zz = z + rise * (v ** 1.35) + corner * (abs(u) ** 6) * ((1 - v) ** 3)
                verts.append((x, y, zz))
        faces = []
        for j in range(nv):
            for i in range(nx):
                a = j * (nx + 1) + i
                faces.append((a, a + 1, a + nx + 2, a + nx + 1))
        b.poly(p["roof"], verts, faces, up=True)
        for i in range(-3, 4):
            x = cx + hw * i / 4
            points = []
            for j in range(6):
                v = j / 5
                points.append((x, cy + sign * hd * (1 - v), z + rise * v ** 1.35 + corner * (abs((x - cx) / hw) ** 6) * (1 - v) ** 3 + 0.035))
            for a, bb in zip(points, points[1:]):
                b.beam(p["roof"], a, bb, 0.035, 6)
        for side in (-1, 1):
            points = []
            for i in range(9):
                u = -1 + 2 * i / 8
                points.append((cx + hw * u, cy + sign * hd, z + corner * abs(u) ** 6))
            for a, bb in zip(points, points[1:]):
                b.beam(p["dark"], a, bb, 0.075, 8)
    b.beam(p["dark"], (cx - hw - 0.15, cy, z + rise + 0.06), (cx + hw + 0.15, cy, z + rise + 0.06), 0.11, 10)
    for side in (-1, 1):
        b.beam(p["gold"], (cx + side * (hw - 0.2), cy, z + rise + 0.08),
               (cx + side * (hw + 0.45), cy, z + rise + 0.42), 0.055, 8)


def silhouette_roof(b, p, width, depth, z, rise=1.1, center=(0, 0), corner=0.25):
    """Distant eaves only: broad readable planes, no close-up tile ribs."""
    cx, cy = center
    hw, hd = width / 2, depth / 2
    verts = [(cx - hw, cy - hd, z + corner), (cx + hw, cy - hd, z + corner),
             (cx + hw, cy + hd, z + corner), (cx - hw, cy + hd, z + corner),
             (cx - hw * 0.92, cy, z + rise), (cx + hw * 0.92, cy, z + rise)]
    b.poly(p["roof"], verts, [(0, 1, 5, 4), (4, 5, 2, 3), (0, 4, 3), (1, 2, 5)], up=True)
    b.beam(p["dark"], (cx - hw, cy - hd, z + corner), (cx + hw, cy - hd, z + corner), 0.055, 6)
    b.beam(p["dark"], (cx - hw * 0.96, cy, z + rise + 0.03), (cx + hw * 0.96, cy, z + rise + 0.03), 0.065, 6)


def hip_roof(b, p, width, depth, z, rise=1.8, corner=0.55):
    hw, hd = width / 2, depth / 2
    tw, td = hw * 0.24, hd * 0.24
    for side in range(4):
        verts = []
        nu, nv = 8, 5
        for j in range(nv + 1):
            v = j / nv
            for i in range(nu + 1):
                u = -1 + 2 * i / nu
                if side == 0:
                    x, y = u * (hw * (1 - v) + tw * v), -hd * (1 - v) - td * v
                elif side == 1:
                    x, y = u * (hw * (1 - v) + tw * v), hd * (1 - v) + td * v
                elif side == 2:
                    x, y = -hw * (1 - v) - tw * v, u * (hd * (1 - v) + td * v)
                else:
                    x, y = hw * (1 - v) + tw * v, u * (hd * (1 - v) + td * v)
                zz = z + rise * v ** 1.3 + corner * abs(u) ** 6 * (1 - v) ** 3
                verts.append((x, y, zz))
        faces = []
        for j in range(nv):
            for i in range(nu):
                a = j * (nu + 1) + i
                faces.append((a, a + 1, a + nu + 2, a + nu + 1))
        b.poly(p["roof"], verts, faces, up=True)
        for u in (-0.65, -0.3, 0, 0.3, 0.65):
            points = []
            for j in range(6):
                v = j / 5
                if side == 0:
                    x, y = u * (hw * (1 - v) + tw * v), -hd * (1 - v) - td * v
                elif side == 1:
                    x, y = u * (hw * (1 - v) + tw * v), hd * (1 - v) + td * v
                elif side == 2:
                    x, y = -hw * (1 - v) - tw * v, u * (hd * (1 - v) + td * v)
                else:
                    x, y = hw * (1 - v) + tw * v, u * (hd * (1 - v) + td * v)
                points.append((x, y, z + rise * v ** 1.3 + corner * abs(u) ** 6 * (1 - v) ** 3 + 0.04))
            for a, bb in zip(points, points[1:]):
                b.beam(p["roof"], a, bb, 0.035, 6)
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.beam(p["dark"], (sx * hw, sy * hd, z + corner), (sx * tw, sy * td, z + rise + 0.05), 0.08, 8)
            b.beam(p["gold"], (sx * (hw - 0.2), sy * (hd - 0.2), z + corner),
                   (sx * (hw + 0.5), sy * (hd + 0.5), z + corner + 0.45), 0.05, 8)
    b.box(p["dark"], (tw * 2.2, td * 2.2, 0.18), (0, 0, z + rise), bevel=0.03)


def railing(b, p, a, bb, z_func=None, post_spacing=1.4, height=0.85):
    a, bb = Vector(a), Vector(bb)
    length = (bb - a).length
    count = max(1, math.ceil(length / post_spacing))
    points = []
    for i in range(count + 1):
        v = a.lerp(bb, i / count)
        z = z_func(v.x, v.y) if z_func else v.z
        b.box(p["stone"], (0.22, 0.22, height), (v.x, v.y, z + height / 2), bevel=0.025)
        b.box(p["stone"], (0.3, 0.3, 0.1), (v.x, v.y, z + height), bevel=0.02)
        points.append((v.x, v.y, z))
    for p0, p1 in zip(points, points[1:]):
        b.beam(p["stone"], (p0[0], p0[1], p0[2] + height * 0.82),
               (p1[0], p1[1], p1[2] + height * 0.82), 0.085, 8)
        b.beam(p["stone"], (p0[0], p0[1], p0[2] + height * 0.36),
               (p1[0], p1[1], p1[2] + height * 0.36), 0.055, 8)


def street_railing(b, p, a, bb):
    """Low-cost near-ground stone rail; the hero bridge keeps the rounded version."""
    a, bb = Vector(a), Vector(bb)
    length = (bb - a).length
    count = max(1, math.ceil(length / 2.4))
    points = []
    for i in range(count + 1):
        v = a.lerp(bb, i / count)
        b.box(p["stone"], (0.18, 0.18, 0.7), (v.x, v.y, v.z + 0.35), bevel=0)
        b.box(p["stone"], (0.26, 0.26, 0.08), (v.x, v.y, v.z + 0.7), bevel=0)
        points.append(v)
    for p0, p1 in zip(points, points[1:]):
        for z, thick in ((0.58, 0.11), (0.28, 0.075)):
            delta = p1 - p0
            b.box(p["stone"], (delta.length, thick, thick), (p0 + p1) / 2 + Vector((0, 0, z)),
                  rot=(0, 0, math.atan2(delta.y, delta.x)), bevel=0)


def build_riverbanks(scene, p):
    b = Builder()
    for side in (-1, 1):
        b.box(p["stone"], (180, 27, 1.2), (0, side * 25.5, -0.02), bevel=0.04)
        b.box(p["dark"], (180, 6.0, 0.035), (0, side * 18, 0.60), bevel=0)
        for x in range(-89, 90, 2):
            b.box(p["stone"], (1.92, 0.65, 0.18), (x, side * 12.05, 0.65), bevel=0.035)
            b.box(p["stone"], (1.9, 0.5, 1.15), (x, side * 12.18, 0.05), bevel=0.025)
        for x in range(-88, 89, 4):
            for y in (15.3, 18, 20.7):
                b.box(p["stone"], (3.88, 2.55, 0.045), (x, side * y, 0.625), bevel=0.012)
    # Low-key distant eaves, behind the usable streets.
    for x, side, w in ((-78, 1, 11), (-48, 1, 10), (-20, 1, 12), (31, 1, 10), (68, 1, 12),
                       (-70, -1, 12), (-30, -1, 10), (5, -1, 11), (40, -1, 12), (75, -1, 10)):
        b.box(p["dark"], (w, 6, 4.5), (x, side * 32, 2.85), bevel=0.03)
        silhouette_roof(b, p, w + 1.2, 7.4, 5.1, 1.35, center=(x, side * 32), corner=0.25)
    # A second, quieter roofline closes the horizon without competing with the tower.
    for i, (x, side, w, h) in enumerate(((-84, 1, 9, 4.2), (-61, 1, 12, 5.0), (-35, 1, 9, 4.0),
                                        (-7, 1, 13, 5.3), (22, 1, 10, 4.4), (53, 1, 12, 5.0),
                                        (86, 1, 10, 4.1), (-51, -1, 11, 4.6), (-10, -1, 12, 4.0),
                                        (25, -1, 10, 5.1), (61, -1, 12, 4.3))):
        y = side * 36.0
        b.box(p["plaster"], (w, 5.0, h), (x, y, 0.58 + h / 2), bevel=0.02)
        b.box(p["dark"], (w + 0.2, 5.2, 0.24), (x, y, 0.85), bevel=0.01)
        silhouette_roof(b, p, w + 0.9, 6.0, h + 0.65, 1.15, center=(x, y), corner=0.28)
        if i % 2 == 0:
            b.box(p["paper"], (w * 0.34, 0.06, 1.0), (x, y - side * 2.53, 2.3), bevel=0)
    # Close-range stone balustrades frame the water; openings preserve bridge and quay access.
    for side in (-1, 1):
        for xa, xb in ((-82, 79), (97, 118), (132, 175)) if side == 1 else ((-82, 78), (100, 170)):
            street_railing(b, p, (xa - 90, side * 12.45, 0.67), (xb - 90, side * 12.45, 0.67))
    # Warm-edged paving bands and drainage lines break up the formerly empty grey ground.
    for side in (-1, 1):
        for x in range(-86, 87, 3):
            for y in (14.0, 16.2):
                b.box(p["stone"], (2.82, 1.95, 0.055), (x, side * y, 0.655), bevel=0)
            b.box(p["dark"], (2.7, 0.12, 0.035), (x, side * 17.35, 0.66), bevel=0)
        for x in (-68, -42, -16, 18, 48, 108, 142):
            y = side * 14.0
            b.box(p["wood"], (1.5, 0.55, 0.16), (x, y, 1.02), bevel=0.025)
            for dx in (-0.58, 0.58):
                b.box(p["dark"], (0.13, 0.45, 0.42), (x + dx, y, 0.82), bevel=0.015)
    # Willows: dark, slender foliage rather than bright spherical trees.
    for x, side in ((-82, -1), (-35, 1), (22, -1), (78, 1), (-20, -1), (82, -1)):
        y = side * 13.4
        b.cyl(p["wood"], 0.22, 4.3, (x, y, 2.7), vertices=9, radius2=0.13)
        for k in range(9):
            a = k * TAU / 9
            tip = (x + math.cos(a) * 1.8, y + math.sin(a) * 1.8, 4.2 + 0.3 * math.sin(a * 2))
            b.beam(p["wood"], (x, y, 3.8), tip, 0.055, 7)
            for j in range(3):
                xx = tip[0] + math.cos(a) * j * 0.25
                yy = tip[1] + math.sin(a) * j * 0.25
                b.blob(p["foliage"], 0.45, (xx, yy, tip[2] - j * 0.65), (0.55, 0.55, 1.6), 1)
    return build_resource(scene, "model-riverbanks", b)


def build_paifang(scene, p, font):
    b = Builder()
    for x in (-4.5, -2.7, 2.7, 4.5):
        b.box(p["stone"], (0.75, 0.75, 0.45), (x, 0, 0.23), bevel=0.05)
        b.cyl(p["red"], 0.24, 5.4 if abs(x) < 3 else 4.4, (x, 0, 2.9), vertices=12)
        for z in (0.65, 3.8):
            b.cyl(p["gold"], 0.29, 0.12, (x, 0, z), vertices=12)
    b.box(p["dark"], (10.2, 0.45, 0.4), (0, 0, 4.25), bevel=0.04)
    b.box(p["red"], (6.3, 0.5, 0.48), (0, 0, 5.25), bevel=0.04)
    b.box(p["gold"], (3.2, 0.16, 0.9), (0, -0.31, 4.83), bevel=0.035)
    b.box(p["dark"], (3.0, 0.18, 0.72), (0, -0.42, 4.83), bevel=0.025)
    for x in (-3.6, 3.6):
        gable_roof(b, p, 3.4, 2.3, 4.45, 0.85, center=(x, 0), corner=0.3)
    gable_roof(b, p, 7.0, 2.7, 5.5, 1.15, corner=0.42)
    # Three clearly articulated bays, with two luminous layers framing the central vista.
    for x in (-3.6, 3.6):
        b.box(p["red"], (3.25, 0.34, 0.26), (x, 0, 3.72), bevel=0.025)
        b.box(p["gold"], (2.7, 0.08, 0.07), (x, -0.22, 3.72), bevel=0.01)
    for x in (-3.6, 0, 3.6):
        for y, z, r in ((-0.58, 3.38, 0.29), (-0.46, 4.25, 0.23)):
            lantern(b, p, (x, y, z), r, r * 2.35)
    for x in (-4.5, -2.7, 2.7, 4.5):
        for z in (1.7, 2.45, 3.15):
            lantern(b, p, (x, -0.42, z), 0.16, 0.36)
    for x in (-1.4, 0, 1.4):
        b.box(p["gold"], (0.055, 0.05, 0.44), (x, -0.53, 4.82), bevel=0.008)
    root = build_resource(scene, "model-paifang", b, -math.pi / 2)
    add_label(root, "上元灯夜", (0, -0.53, 4.85), 0.52, font=font, mat=p["gold"])
    root["collision"] = "four cylinder column proxies; keep central 4.8m passage clear"
    return root


def deck_height(y):
    return 0.72 + 3.05 * max(0, 1 - (y / 14.8) ** 2)


def arch_height(y):
    return 0.25 + 2.75 * math.sqrt(max(0, 1 - (y / 11.2) ** 2))


def build_bridge(scene, p):
    b = Builder()
    verts, faces = [], []
    steps = 40
    for i in range(steps + 1):
        y = -11.2 + 22.4 * i / steps
        za, zd = arch_height(y), deck_height(y)
        verts.extend([(-3.1, y, za), (3.1, y, za), (-3.1, y, zd), (3.1, y, zd)])
    for i in range(steps):
        a, n = i * 4, (i + 1) * 4
        faces.extend([(a, n, n + 2, a + 2), (a + 1, a + 3, n + 3, n + 1),
                      (a + 2, n + 2, n + 3, a + 3), (a, a + 1, n + 1, n)])
    faces.extend([(0, 2, 3, 1), (steps * 4, steps * 4 + 1, steps * 4 + 3, steps * 4 + 2)])
    b.poly(p["stone"], verts, faces)
    # Radial voussoirs make the single arch legible at close range.
    for side in (-1, 1):
        for i in range(25):
            y0 = -11.0 + 22.0 * (i + 0.5) / 25
            z = arch_height(y0) + 0.06
            slope = (arch_height(min(11.19, y0 + 0.03)) - arch_height(max(-11.19, y0 - 0.03))) / 0.06
            b.box(p["stone"], (0.18, 0.82, 0.28), (side * 3.16, y0, z),
                  rot=(math.atan(slope), 0, 0), bevel=0.025)
        railing(b, p, (side * 2.85, -14.7, 0), (side * 2.85, 14.7, 0), lambda _x, y: deck_height(y), 1.35, 0.95)
        for y in (-13.6, -7.0, 0, 7.0, 13.6):
            z = deck_height(y)
            b.cyl(p["dark"], 0.09, 1.35, (side * 2.85, y, z + 1.35), vertices=8)
            lantern(b, p, (side * 2.85, y, z + 2.05), 0.24, 0.55)
    for side in (-1, 1):
        for i in range(8):
            y = side * (11.35 + i * 0.43)
            z = deck_height(y)
            b.box(p["stone"], (5.9, 0.46, 0.18), (0, y, z - 0.05), bevel=0.018)
    root = build_resource(scene, "model-bridge", b)
    root["collision"] = "24-32 thin deck boxes following deck_height(y); rail boxes; stepped approaches need invisible ramp strips"
    root["walkable_width_m"] = 5.3
    root["arch_clearance_m"] = 3.0
    return root


def dougong(b, p, x, y, z, scale=1):
    for level in range(3):
        s = scale * (1 + level * 0.26)
        b.box(p["red" if level == 0 else "dark"], (0.65 * s, 0.24 * s, 0.16 * scale), (x, y, z + level * 0.16 * scale), bevel=0.015)
        b.box(p["dark"], (0.24 * s, 0.65 * s, 0.16 * scale), (x, y, z + level * 0.16 * scale), bevel=0.015)


def lantern_wheel(root, p, name, loc, radius):
    c = root.users_collection[0]
    pivot = bpy.data.objects.new("pivot-" + name, None)
    c.objects.link(pivot)
    pivot.parent = root
    pivot.location = loc
    pivot.empty_display_size = 0.25
    pivot["dynamic"] = 1
    pivot["pivot"] = "lantern-wheel"
    pivot["axis"] = "Z"
    b = Builder()
    b.torus(p["gold"], radius, 0.055, (0, 0, 0), (math.pi / 2, 0, 0), 28, 6)
    for i in range(8):
        a = TAU * i / 8
        x, z = math.cos(a) * radius, math.sin(a) * radius
        b.beam(p["gold"], (0, 0, 0), (x, 0, z), 0.025, 6)
        lantern(b, p, (x, 0, z), 0.18, 0.42)
    mesh = bpy.data.meshes.new(name)
    b.bm.to_mesh(mesh)
    b.bm.free()
    for m in b.mats:
        mesh.materials.append(m)
    obj = bpy.data.objects.new(name, mesh)
    c.objects.link(obj)
    obj.parent = pivot
    obj["dynamic"] = 1
    obj["emissive_group"] = "tower-wheel"
    return pivot


def build_tower(scene, p, font):
    b = Builder()
    b.box(p["stone"], (12, 12, 0.65), (0, 0, 0.325), bevel=0.08)
    b.box(p["stone"], (11.4, 11.4, 0.22), (0, 0, 0.76), bevel=0.04)
    levels = [(9.2, 0.85, 4.25), (7.4, 5.0, 8.0), (5.7, 9.0, 11.7)]
    for level, (width, bottom, top) in enumerate(levels):
        b.box(p["plaster"], (width - 0.7, width - 0.7, top - bottom), (0, 0, (top + bottom) / 2), bevel=0.025)
        for x in (-width / 2, width / 2):
            for y in (-width / 2, width / 2):
                b.cyl(p["red"], 0.19, top - bottom + 0.5, (x, y, (top + bottom) / 2), vertices=12)
                dougong(b, p, x, y, top, 1.0 if level == 0 else 0.85)
        for side in (-1, 1):
            lattice(b, p, (0, side * (width / 2 - 0.3), (top + bottom) / 2), width * 0.55, (top - bottom) * 0.56)
            lattice(b, p, (side * (width / 2 - 0.3), 0, (top + bottom) / 2), width * 0.55, (top - bottom) * 0.56, True)
        platform = width + 1.7
        b.box(p["dark"], (platform, platform, 0.25), (0, 0, top + 0.03), bevel=0.025)
        if level < 2:
            for side in (-1, 1):
                railing(b, p, (-platform / 2, side * platform / 2, top + 0.17),
                        (platform / 2, side * platform / 2, top + 0.17), None, 1.5, 0.72)
                railing(b, p, (side * platform / 2, -platform / 2, top + 0.17),
                        (side * platform / 2, platform / 2, top + 0.17), None, 1.5, 0.72)
            hip_roof(b, p, platform + 1.0, platform + 1.0, top + 0.8, 1.15, 0.42)
    hip_roof(b, p, 8.0, 8.0, 12.45, 2.45, 0.62)
    b.cyl(p["gold"], 0.13, 1.05, (0, 0, 15.35), vertices=10, radius2=0.04)
    b.blob(p["gold"], 0.22, (0, 0, 15.0), subdivisions=2)
    b.box(p["dark"], (3.5, 0.18, 0.82), (0, -4.85, 3.75), bevel=0.03)
    root = build_resource(scene, "model-lantern-tower", b)
    add_label(root, "上元灯楼", (0, -4.97, 3.77), 0.48, font=font, mat=p["gold"])
    lantern_wheel(root, p, "lantern-wheel-01", (0, -5.75, 6.6), 1.15)
    lantern_wheel(root, p, "lantern-wheel-02", (0, -4.55, 10.1), 0.88)
    root["collision"] = "12x12 base box; three stories are exterior-only, no interior collision required"
    return root


SHOP_NAMES = ["花灯", "茶肆", "酒坊", "绸庄", "纸扎", "听雨楼"]


def build_shop(scene, p, font, index):
    b = Builder()
    widths = [8.0, 9.0, 8.5, 9.5, 8.0, 12.0]
    depths = [6.5, 7.0, 6.0, 7.0, 6.5, 9.0]
    w, d = widths[index - 1], depths[index - 1]
    two = index in (2, 4, 6)
    wall_top = 6.7 if two else 3.65
    b.box(p["stone"], (w + 0.4, d + 0.4, 0.45), (0, 0, 0.225), bevel=0.045)
    b.box(p["plaster"], (w - 0.35, 0.22, wall_top - 0.45), (0, d / 2 - 0.11, (wall_top + 0.45) / 2), bevel=0.015)
    for side in (-1, 1):
        b.box(p["plaster"], (0.22, d - 0.25, wall_top - 0.45), (side * (w / 2 - 0.11), 0, (wall_top + 0.45) / 2), bevel=0.015)
        # Large architectural divisions replace blank white side walls.
        b.box(p["stone"], (0.32, d + 0.1, 0.62), (side * (w / 2 + 0.03), 0, 0.76), bevel=0.025)
        for z in (1.12, 3.25, wall_top - 0.15):
            if z < wall_top:
                b.box(p["dark"], (0.3, d + 0.2, 0.18), (side * (w / 2 + 0.04), 0, z), bevel=0.015)
        for y in (-d / 2, -d / 6, d / 6, d / 2):
            b.box(p["wood"], (0.32, 0.24, wall_top - 0.35), (side * (w / 2 + 0.05), y, (wall_top + 0.45) / 2), bevel=0.02)
        for y in (-d * 0.28, d * 0.28):
            lattice(b, p, (side * (w / 2 + 0.13), y, 2.05), min(1.65, d * 0.23), 1.5, True)
            if two:
                lattice(b, p, (side * (w / 2 + 0.13), y, 4.95), min(1.55, d * 0.22), 1.45, True)
    b.box(p["stone"], (w + 0.15, 0.32, 0.62), (0, d / 2 + 0.02, 0.76), bevel=0.025)
    for x in (-w / 2, -w / 6, w / 6, w / 2):
        b.box(p["wood"], (0.25, 0.3, wall_top - 0.35), (x, d / 2 + 0.03, (wall_top + 0.45) / 2), bevel=0.02)
    for x in (-w * 0.28, w * 0.28):
        lattice(b, p, (x, d / 2 + 0.13, 2.05), 1.6, 1.45)
    b.box(p["wood"], (w - 0.25, 0.22, wall_top - 0.45), (0, -d / 2 + 0.11, (wall_top + 0.45) / 2), bevel=0.015)
    bays = 4 if index == 6 else 3
    for k in range(bays + 1):
        x = -w / 2 + w * k / bays
        b.box(p["dark"], (0.23, 0.28, wall_top + 0.15), (x, -d / 2, wall_top / 2), bevel=0.025)
        b.box(p["stone"], (0.38, 0.4, 0.35), (x, -d / 2, 0.55), bevel=0.03)
        dougong(b, p, x, -d / 2, wall_top - 0.1, 0.7)
    for z in (0.65, 3.15, wall_top):
        if z <= wall_top:
            b.box(p["dark"], (w + 0.2, 0.28, 0.2), (0, -d / 2, z), bevel=0.02)
    # Ground-floor centre door and flanking illuminated lattice windows.
    b.box(p["dark"], (1.5, 0.16, 2.45), (0, -d / 2 - 0.15, 1.68), bevel=0.02)
    for x in (-0.32, 0.32):
        b.box(p["wood"], (0.58, 0.08, 2.18), (x, -d / 2 - 0.25, 1.62), bevel=0.01)
        b.torus(p["gold"], 0.055, 0.012, (x * 0.35, -d / 2 - 0.31, 1.6), (math.pi / 2, 0, 0), 10, 4)
    for x in (-w * 0.31, w * 0.31):
        lattice(b, p, (x, -d / 2 - 0.15, 1.85), min(1.75, w * 0.22), 1.5)
    if two:
        for x in (-w * 0.3, 0, w * 0.3):
            lattice(b, p, (x, -d / 2 - 0.16, 4.95), min(1.55, w * 0.2), 1.65)
        b.box(p["dark"], (w + 0.8, 1.0, 0.16), (0, -d / 2 - 0.35, 3.65), bevel=0.02)
        railing(b, p, (-w / 2, -d / 2 - 0.8, 3.73), (w / 2, -d / 2 - 0.8, 3.73), None, 1.2, 0.72)
    # Side lattice is important on the corner tea house.
    if index == 6:
        for y in (-2.7, 0, 2.7):
            lattice(b, p, (w / 2 + 0.04, y, 4.95), 1.7, 1.65, True)
            b.box(p["dark"], (0.22, 0.22, 6.5), (w / 2, y - 0.95, 3.5), bevel=0.02)
        b.box(p["dark"], (1.1, d + 0.5, 0.16), (w / 2 + 0.35, 0, 3.65), bevel=0.02)
        gable_roof(b, p, w + 1.7, d + 1.8, 3.75, 0.65, corner=0.25)
    b.box(p["dark"], (2.6 if index < 6 else 4.0, 0.18, 0.75), (0, -d / 2 - 0.32, 2.95 if not two else 3.0), bevel=0.025)
    if index in (1, 3, 5):
        b.box(p["red"], (w * 0.78, 1.65, 0.08), (0, -d / 2 - 0.85, 2.7), rot=(0.16, 0, 0), bevel=0.015)
        for x in (-w * 0.36, w * 0.36):
            b.cyl(p["wood"], 0.055, 2.4, (x, -d / 2 - 1.55, 1.5), vertices=8)
    gable_roof(b, p, w + 1.6, d + 1.7, wall_top + 0.2, 1.55 if index != 6 else 1.85, corner=0.4)
    for x in (-w / 2 + 0.65, w / 2 - 0.65):
        b.beam(p["dark"], (x, -d / 2 - 0.05, 3.0), (x, -d / 2 - 0.55, 3.0), 0.04, 8)
        lantern(b, p, (x, -d / 2 - 0.62, 2.55), 0.25, 0.58)
    if index == 6:
        # A short perpendicular wing gives the tea house a true corner silhouette.
        b.box(p["plaster"], (3.2, 4.5, 3.0), (w / 2 - 0.8, d / 2 + 1.5, 2.0), bevel=0.02)
        gable_roof(b, p, 4.4, 5.4, 3.6, 1.0, center=(w / 2 - 0.8, d / 2 + 1.5), corner=0.25)
    # Continuous market frontage: striped cloth, scalloped valance, vertical signs and layered lamps.
    awning_y = -d / 2 - 1.0
    strips = 10 if index == 6 else 8
    for i in range(strips):
        x0 = -w * 0.43 + w * 0.86 * i / strips
        b.box(p["red"] if i % 2 == 0 else p["paper"], (w * 0.86 / strips + 0.025, 1.65, 0.055),
              (x0 + w * 0.43 / strips, awning_y, 2.78), rot=(0.13, 0, 0), bevel=0.008)
        b.box(p["red"] if i % 2 == 0 else p["paper"], (w * 0.86 / strips + 0.025, 0.06, 0.25),
              (x0 + w * 0.43 / strips, awning_y - 0.82, 2.58), bevel=0.01)
    for x in (-w * 0.39, w * 0.39):
        b.beam(p["dark"], (x, -d / 2 - 0.1, 3.55), (x, -d / 2 - 1.15, 3.55), 0.045, 8)
        banner(b, p, (x, -d / 2 - 1.18, 2.38), 0.55, 1.55)
    for x in (-w * 0.23, w * 0.23):
        lantern(b, p, (x, -d / 2 - 0.64, 2.36), 0.2, 0.48)
        if two:
            lantern(b, p, (x, -d / 2 - 0.42, 5.95), 0.18, 0.43)
    # A bracketed vertical shop sign is readable as a major shape at street distance.
    sx = -w / 2 + 0.5
    b.beam(p["dark"], (sx, -d / 2, 4.15), (sx, -d / 2 - 1.1, 4.15), 0.045, 8)
    b.box(p["red"], (0.68, 0.09, 1.65), (sx, -d / 2 - 1.12, 3.25), bevel=0.025)
    root = build_resource(scene, f"model-shop-{index:02d}", b)
    add_label(root, SHOP_NAMES[index - 1], (0, -d / 2 - 0.43, 2.97 if not two else 3.02),
              0.45 if index < 6 else 0.62, font=font, mat=p["gold"])
    add_label(root, "\n".join(SHOP_NAMES[index - 1]), (sx, -d / 2 - 1.18, 3.26),
              0.4, font=font, mat=p["gold"])
    root["collision"] = "exterior shell boxes and column proxies; ground-floor door is decorative, no interior"
    root["shop_variant"] = SHOP_NAMES[index - 1]
    return root


def build_stall(scene, p, font, kind):
    b = Builder()
    w, d = (4.6, 2.8) if kind == "riddle" else (4.2, 3.2)
    b.box(p["wood"], (w, d, 0.18), (0, 0, 0.55), bevel=0.025)
    for x in (-w / 2 + 0.2, w / 2 - 0.2):
        for y in (-d / 2 + 0.15, d / 2 - 0.15):
            b.cyl(p["dark"], 0.075, 2.6, (x, y, 1.85), vertices=8)
    b.box(p["wood"], (w - 0.3, 0.75, 0.16), (0, -d / 2 + 0.45, 1.25), bevel=0.025)
    b.box(p["red"] if kind == "riddle" else p["paper"], (w + 0.45, d + 0.6, 0.09), (0, 0, 3.1), rot=(0, 0.05, 0), bevel=0.02)
    for x in (-1.4, 0, 1.4):
        lantern(b, p, (x, -d / 2 - 0.2, 2.55), 0.22, 0.5)
    if kind == "riddle":
        for i in range(7):
            x = -1.8 + i * 0.6
            b.beam(p["gold"], (x, 0.7, 2.95), (x, 0.7, 2.25), 0.012, 6)
            b.box(p["paper"], (0.34, 0.025, 0.48), (x, 0.7, 2.15), bevel=0.005)
    else:
        for x in (-0.8, 0, 0.8):
            b.cyl(p["stone"], 0.18, 0.28, (x, -0.55, 1.48), vertices=12, radius2=0.22)
        b.cyl(p["dark"], 0.32, 0.55, (0.9, 0.6, 1.0), vertices=12)
    # Countertop stories: readable trays, paper goods, ceramics and tea-making tools.
    b.box(p["dark"], (w - 0.55, 0.92, 0.09), (0, -d / 2 + 0.42, 1.38), bevel=0.02)
    if kind == "riddle":
        for i, x in enumerate((-1.45, -0.8, 0.0)):
            for j in range(2 + i % 2):
                b.box(p["paper"] if j % 2 else p["red"], (0.48, 0.38, 0.07),
                      (x, -0.87, 1.47 + j * 0.075), rot=(0, 0, 0.08 * (i - 1)), bevel=0.008)
        b.box(p["dark"], (0.52, 0.32, 0.07), (0.85, -0.87, 1.47), bevel=0.015)
        b.cyl(p["stone"], 0.16, 0.32, (1.45, -0.82, 1.58), vertices=12)
        for i in range(4):
            b.beam(p["wood"], (1.4 + i * 0.035, -0.82, 1.65), (1.34 + i * 0.06, -0.79, 2.03), 0.013, 6)
        for x in (-1.35, 1.35):
            mini_lotus(b, p, (x, 0.35, 1.35), 0.75, x)
    else:
        b.box(p["wood"], (1.65, 0.72, 0.055), (-0.35, -0.75, 1.47), bevel=0.025)
        b.blob(p["stone"], 0.28, (-0.42, -0.72, 1.72), (1, 1, 0.85), 2)
        b.cyl(p["stone"], 0.12, 0.13, (-0.42, -0.72, 1.94), vertices=12)
        b.beam(p["stone"], (-0.2, -0.72, 1.75), (0.08, -0.72, 1.87), 0.075, 10)
        b.torus(p["stone"], 0.21, 0.035, (-0.68, -0.72, 1.75), (math.pi / 2, 0, 0), 14, 6)
        for x in (0.3, 0.72, 1.15):
            b.cyl(p["paper"], 0.105, 0.17, (x, -0.8, 1.56), vertices=12, radius2=0.13)
        for x in (-1.45, 1.45):
            b.cyl(p["wood"], 0.25, 0.6, (x, 0.55, 1.02), vertices=12)
            b.cyl(p["dark"], 0.27, 0.07, (x, 0.55, 1.35), vertices=12)
    banner(b, p, (-w / 2 - 0.18, -d / 2 + 0.2, 2.0), 0.48, 1.45)
    resource = "model-stall-" + kind
    root = build_resource(scene, resource, b)
    add_label(root, "灯谜" if kind == "riddle" else "茶汤", (0, -d / 2 - 0.32, 2.98), 0.38, font=font, mat=p["gold"])
    root["interaction"] = "riddle" if kind == "riddle" else "tea-rest"
    return root


def build_lantern_array(scene, p, index):
    b = Builder()
    for side in (-1, 1):
        b.box(p["stone"], (0.65, 0.65, 0.35), (0, side * 13.1, 0.75), bevel=0.05)
        b.cyl(p["dark"], 0.12, 5.1, (0, side * 13.1, 3.15), vertices=10, radius2=0.085)
        b.cyl(p["gold"], 0.18, 0.12, (0, side * 13.1, 5.72), vertices=10)
    points = []
    for i in range(25):
        y = -13.1 + 26.2 * i / 24
        z = 5.65 - 1.45 * (1 - (y / 13.1) ** 2)
        points.append((0, y, z))
    for a, bb in zip(points, points[1:]):
        b.beam(p["dark"], a, bb, 0.025, 6)
    for i in range(9):
        y = -11.6 + 23.2 * i / 8
        z = 5.65 - 1.45 * (1 - (y / 13.1) ** 2)
        length = 0.4 + 0.18 * ((i + index) % 3)
        b.beam(p["dark"], (0, y, z), (0, y, z - length), 0.018, 6)
        lantern(b, p, (0, y, z - length - 0.38), 0.26 + 0.035 * ((i + index) % 2), 0.68)
    # Street-scale festival layers run perpendicular to the shopfronts and across the river.
    for lane, dx in enumerate((-6.0, 0.0, 6.0)):
        z = 5.15 + 0.25 * ((lane + index) % 2)
        for y in (12.9, 22.0):
            b.cyl(p["dark"], 0.075, z - 0.6, (dx, y, (z + 0.6) / 2), vertices=8)
            b.box(p["stone"], (0.34, 0.34, 0.25), (dx, y, 0.72), bevel=0.025)
        festoon(b, p, (dx, 12.9, z), (dx, 22.0, z), 6, 0.65, 0.18, 0.32)
        for y in (13.05, 21.85):
            for k in range(3):
                lantern(b, p, (dx, y, 3.4 - k * 0.55), 0.13, 0.3)
        banner(b, p, (dx, 21.75, 3.65), 0.55, 1.7, mat=p["red"] if lane % 2 else p["paper"])
    if index == 1:
        # A nested pair of lantern gates wraps the spawn view before the paifang.
        for dx in (-25.0, -10.0):
            for y in (13.6, 22.4):
                b.box(p["stone"], (0.48, 0.48, 0.32), (dx, y, 0.76), bevel=0.035)
                b.cyl(p["red"], 0.13, 4.8, (dx, y, 3.05), vertices=10)
            for z in (4.35, 5.2):
                festoon(b, p, (dx, 13.6, z), (dx, 22.4, z), 7, 0.5, 0.2, 0.25)
            for y in (14.2, 21.8):
                for k in range(4):
                    lantern(b, p, (dx, y, 3.65 - 0.58 * k), 0.15, 0.34)
    root = build_resource(scene, f"model-lantern-array-s{index}", b)
    root["collision"] = "bank and street edge pole cylinders only; central route and overhead catenaries remain clear"
    return root


def build_lotus(scene, p):
    b = Builder()
    for ring, count, radius in ((0, 8, 0.48), (1, 6, 0.3)):
        for i in range(count):
            a = TAU * (i + ring * 0.5) / count
            verts = [(0, 0, 0.04 + ring * 0.05),
                     (radius * 0.45, -0.14, 0.10), (radius, 0, 0.20 + ring * 0.05),
                     (radius * 0.45, 0.14, 0.10)]
            b.poly(p["red"] if ring == 0 else p["paper"], verts, [(0, 1, 2, 3)], rot=(0, 0, a))
    b.cyl(p["lantern"], 0.16, 0.35, (0, 0, 0.27), vertices=12)
    b.cyl(p["gold"], 0.18, 0.04, (0, 0, 0.09), vertices=12)
    root = build_resource(scene, "model-river-lantern-lotus", b)
    root["dynamic"] = 1
    root["prototype"] = "player-release"
    root["water_origin"] = "local Z=0 at waterline"
    return root


def build_paperboat(scene, p):
    b = Builder()
    verts = [(-0.75, 0, 0.28), (0.75, 0, 0.28), (0.48, -0.32, 0.02), (-0.48, -0.32, 0.02),
             (0.48, 0.32, 0.02), (-0.48, 0.32, 0.02), (0, 0, 0.62)]
    b.poly(p["paper"], verts, [(0, 2, 6), (2, 1, 6), (1, 4, 6), (4, 0, 6), (0, 5, 2), (1, 3, 4), (2, 5, 3, 4)])
    b.cyl(p["lantern"], 0.11, 0.25, (0, 0, 0.28), vertices=10)
    for v in b.bm.verts:
        v.co *= 0.65
    root = build_resource(scene, "model-river-lantern-paperboat", b)
    root["dynamic"] = 1
    root["prototype"] = "player-release"
    root["water_origin"] = "local Z=0 at waterline"
    return root


def build_fish(scene, p):
    b = Builder()
    b.blob(p["red"], 0.65, (0, 0, 0.3), (1.35, 0.55, 0.55), 2)
    b.blob(p["lantern"], 0.43, (0.1, 0, 0.37), (1.1, 0.65, 0.6), 2)
    b.poly(p["red"], [(-0.65, 0, 0.3), (-1.2, -0.48, 0.1), (-1.05, 0, 0.55), (-1.2, 0.48, 0.1)], [(0, 1, 2), (0, 2, 3)])
    for side in (-1, 1):
        b.poly(p["gold"], [(0.1, side * 0.25, 0.32), (-0.35, side * 0.72, 0.1), (-0.45, side * 0.22, 0.25)], [(0, 1, 2)])
        b.blob(p["gold"], 0.055, (0.62, side * 0.27, 0.46), subdivisions=1)
        b.beam(p["gold"], (0.7, side * 0.12, 0.3), (1.08, side * 0.38, 0.18), 0.012, 6)
    for i in range(4):
        b.poly(p["red"], [(-0.35 + i * 0.2, 0, 0.62), (-0.25 + i * 0.2, 0, 0.9 - i * 0.06), (-0.05 + i * 0.2, 0, 0.64)], [(0, 1, 2)])
    root = build_resource(scene, "model-river-lantern-fish", b)
    root["dynamic"] = 1
    root["prototype"] = "player-release"
    root["water_origin"] = "local Z=0 at waterline"
    return root


def hull(b, p, length, width, height=0.65):
    verts = []
    sections = 10
    for i in range(sections + 1):
        x = -length / 2 + length * i / sections
        taper = max(0.08, math.sin(math.pi * i / sections) ** 0.55)
        y = width / 2 * taper
        verts.extend([(x, -y, height), (x, y, height), (x, -y * 0.65, 0), (x, y * 0.65, 0)])
    faces = []
    for i in range(sections):
        a, n = i * 4, (i + 1) * 4
        faces.extend([(a, n, n + 2, a + 2), (a + 1, a + 3, n + 3, n + 1), (a + 2, n + 2, n + 3, a + 3)])
    faces.extend([(0, 2, 3, 1), (sections * 4, sections * 4 + 1, sections * 4 + 3, sections * 4 + 2)])
    b.poly(p["dark"], verts, faces)
    b.box(p["wood"], (length * 0.82, width * 0.78, 0.12), (0, 0, height), bevel=0.025)


def build_boat(scene, p):
    b = Builder()
    hull(b, p, 11, 3.4, 0.72)
    for x in (-3.1, 3.1):
        for y in (-1.15, 1.15):
            b.cyl(p["red"], 0.09, 2.25, (x, y, 1.88), vertices=10)
    b.box(p["wood"], (6.4, 0.16, 1.65), (0, 1.15, 1.85), bevel=0.02)
    b.box(p["wood"], (6.4, 0.16, 1.65), (0, -1.15, 1.85), bevel=0.02)
    for x in (-2.1, 0, 2.1):
        lattice(b, p, (x, -1.25, 1.95), 1.5, 1.2)
        lattice(b, p, (x, 1.25, 1.95), 1.5, 1.2)
    gable_roof(b, p, 7.5, 3.4, 3.0, 0.85, corner=0.3)
    for x in (-4.2, 4.2):
        for y in (-1.15, 1.15):
            lantern(b, p, (x, y, 1.85), 0.25, 0.58)
    railing(b, p, (-4.9, -1.15, 0.85), (-3.5, -1.15, 0.85), None, 0.7, 0.65)
    b.beam(p["gold"], (5.0, 0, 0.85), (5.7, 0, 1.45), 0.06, 8)
    root = build_resource(scene, "model-boat", b)
    root["dynamic"] = 1
    root["water_origin"] = "local Z=0 at waterline; pivot at hull centre"
    return root


def build_skiff(scene, p):
    b = Builder()
    hull(b, p, 5.5, 1.8, 0.45)
    for x in (-1.2, 1.2):
        b.box(p["wood"], (0.28, 1.5, 0.12), (x, 0, 0.62), bevel=0.02)
    b.beam(p["wood"], (-0.6, -0.4, 0.72), (1.8, -1.25, 0.15), 0.045, 8)
    lantern(b, p, (-1.9, 0, 1.0), 0.18, 0.4)
    root = build_resource(scene, "model-skiff", b)
    root["dynamic"] = 1
    root["water_origin"] = "local Z=0 at waterline"
    return root


def build_performance(scene, p):
    b = Builder()
    b.box(p["stone"], (11, 7.5, 0.65), (0, 0, 0.325), bevel=0.06)
    b.box(p["wood"], (10.2, 6.8, 0.28), (0, 0, 0.82), bevel=0.035)
    for x in (-4.4, 4.4):
        for y in (-2.6, 2.6):
            b.cyl(p["red"], 0.15, 4.2, (x, y, 3.0), vertices=12)
            dougong(b, p, x, y, 4.85, 0.85)
    b.box(p["red"], (9.0, 0.18, 3.3), (0, 2.7, 2.7), bevel=0.02)
    for x in (-3.6, -2.8, 2.8, 3.6):
        b.box(p["gold"], (0.12, 0.08, 2.6), (x, 2.58, 2.8), bevel=0.01)
    gable_roof(b, p, 11.3, 8.2, 5.0, 1.55, corner=0.48)
    for x in (-3.7, 0, 3.7):
        lantern(b, p, (x, -2.9, 4.15), 0.34, 0.75)
    b.cyl(p["red"], 0.75, 0.85, (0, 0.6, 1.65), (math.pi / 2, 0, 0), vertices=20)
    for y in (0.15, 1.05):
        b.cyl(p["gold"], 0.79, 0.06, (0, y, 1.65), (math.pi / 2, 0, 0), vertices=20)
    root = build_resource(scene, "model-performance", b, math.pi)
    root["interaction"] = "scheduled river-performance trigger"
    return root


def build_quay(scene, p):
    b = Builder()
    b.box(p["stone"], (8.5, 4.5, 0.5), (0, -3.0, 0.12), bevel=0.05)
    for i in range(7):
        y = 3.25 - i * 0.62
        z = 0.58 - i * 0.065
        b.box(p["stone"], (6.0, 0.65, 0.18), (0, y, z), bevel=0.025)
    for i in range(7):
        y = 3.25 - i * 0.62
        z = 0.58 - i * 0.065
        b.box(p["dark"], (5.95, 0.055, 0.035), (0, y - 0.31, z + 0.1), bevel=0.005)
        for x in (-2.75, 2.75):
            b.box(p["stone"], (0.28, 0.64, 0.28), (x, y, z + 0.02), bevel=0.025)
    for x in (-4.0, 4.0):
        for y in (-4.8, -1.2):
            b.cyl(p["dark"], 0.14, 1.1, (x, y, 0.55), vertices=10)
            b.cyl(p["gold"], 0.19, 0.1, (x, y, 1.12), vertices=10)
        lantern(b, p, (x, -1.0, 2.0), 0.28, 0.62)
        b.cyl(p["dark"], 0.09, 1.6, (x, -1.0, 1.1), vertices=8)
        railing(b, p, (x, -4.8, 0.38), (x, -1.6, 0.38), None, 1.1, 0.62)
    # A side-mounted river-lantern rack leaves the central stair and release route unobstructed.
    for y in (-3.85, -1.75):
        b.cyl(p["wood"], 0.07, 1.8, (3.05, y, 1.25), vertices=8)
    for z in (0.82, 1.35):
        b.box(p["wood"], (1.05, 2.4, 0.1), (3.05, -2.8, z), bevel=0.02)
        for y in (-3.55, -2.8, -2.05):
            mini_lotus(b, p, (3.05, y, z + 0.08), 0.8, y)
    b.beam(p["red"], (3.05, -3.85, 2.18), (3.05, -1.75, 2.18), 0.06, 8)
    for y in (-3.45, -2.8, -2.15):
        lantern(b, p, (3.05, y, 1.93), 0.14, 0.32)
    for x in (-3.1, -2.55):
        b.cyl(p["wood"], 0.24, 0.55, (x, -3.5, 0.67), vertices=12)
        b.cyl(p["dark"], 0.26, 0.06, (x, -3.5, 0.97), vertices=12)
    # Near lotus lamps sit low at the waterline, never as giant floating shades.
    for x, y, s in ((-2.5, -6.0, 1.0), (-1.5, -6.5, 0.8), (0.1, -6.2, 0.9)):
        mini_lotus(b, p, (x, y, 0.03), s, x)
    root = build_resource(scene, "model-quay", b)
    root["interaction"] = "release river lantern"
    root["collision"] = "platform box plus a smooth ramp over seven shallow steps"
    return root


def build_water(scene, p):
    b = Builder()
    nx, ny = 90, 12
    verts = []
    for j in range(ny + 1):
        y = -12 + 24 * j / ny
        for i in range(nx + 1):
            x = -90 + 180 * i / nx
            z = -0.03 + 0.018 * math.sin(x * 0.37 + y * 0.6) * math.sin(y * 0.8)
            verts.append((x, y, z))
    faces = []
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    b.poly(p["water"], verts, faces)
    # Fine, separated vertical families of warm brushstrokes; no broad trapezoid cards.
    rnd = random.Random(2026)
    for world_x in (18, 20, 34, 38, 48, 55, 62, 72, 90, 98, 114, 125, 128, 140, 151, 162):
        cx = world_x - 90
        bank = rnd.choice((-1, 1))
        start = rnd.uniform(2.0, 5.0)
        for k in range(14):
            y = bank * (start + k * rnd.uniform(0.38, 0.55))
            x = cx + rnd.uniform(-0.3, 0.3) + 0.05 * math.sin(k * 1.7)
            # Long, narrow streaks run away from the bank, so they read as vertical light.
            w = rnd.uniform(0.018, 0.045)
            h = rnd.uniform(0.16, 0.5) * (1.0 - k * 0.012)
            b.poly(p["reflection"], [(x - w, y - h, 0.018), (x + w, y - h, 0.018),
                                      (x + w * 0.7, y + h, 0.018), (x - w * 0.7, y + h, 0.018)], [(0, 1, 2, 3)])
    # A sparse static lantern sea belongs to the environment, not to the player prototypes.
    for i in range(46):
        x = -76 + (i % 23) * 6.7 + rnd.uniform(-1.0, 1.0)
        y = (1 if i % 2 else -1) * rnd.uniform(6.4, 10.1)
        mini_lotus(b, p, (x, y, 0.025), rnd.uniform(0.55, 0.85), rnd.uniform(0, TAU))
    root = build_resource(scene, "model-water", b)
    root["realtime"] = 1
    root["no_bake"] = 1
    return root


def point_light(scene, name, loc, energy=90, radius=2.0, hex_value="FFB45C"):
    data = bpy.data.lights.new(name, "POINT")
    data.energy = energy
    data.color = color(hex_value)
    data.shadow_soft_size = radius
    obj = bpy.data.objects.new(name, data)
    scene.collection.children["SY_Environment"].objects.link(obj)
    obj.location = loc


def setup_environment(scene):
    env = bpy.data.collections.new("SY_Environment")
    scene.collection.children.link(env)
    world = bpy.data.worlds.new("SY_DeepBlueNight")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (*color("152842"), 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.72
    scene.world = world
    moon = bpy.data.lights.new("SY_Moon", "SUN")
    moon.energy = 2.35
    moon.color = color("9DBBDD")
    moon.angle = math.radians(12)
    obj = bpy.data.objects.new("SY_Moon", moon)
    env.objects.link(obj)
    obj.rotation_euler = (math.radians(28), math.radians(-22), math.radians(-35))
    fill = bpy.data.lights.new("SY_SkyFill", "AREA")
    fill.energy = 10500
    fill.color = color("6F9CC8")
    fill.shape = "DISK"
    fill.size = 70
    obj = bpy.data.objects.new("SY_SkyFill", fill)
    env.objects.link(obj)
    obj.location = (85, 5, 45)
    for x in (20, 34, 48, 62, 76, 98, 114, 125, 133, 151):
        point_light(scene, "SY_WarmPool", (x, 17 if x != 125 else 7, 4.0), 220, 1.8)
    for x in (38, 72, 128, 162):
        for y in (-8, 8):
            point_light(scene, "SY_LanternPool", (x, y, 3.8), 120, 1.6)
    for x, y, z, power in ((13, 18, 4.0, 280), (20, 18, 4.3, 320), (28, 18, 4.2, 260),
                            (90, 2, 6.0, 180), (98, 18, 7.0, 300), (98, 18, 12.0, 220),
                            (125, 3, 2.5, 170), (128, 17, 4.0, 200)):
        point_light(scene, "SY_FestivalGlow", (x, y, z), power, 2.0)
    for x in (34, 62, 98, 133, 151):
        data = bpy.data.lights.new("SY_StreetWash", "AREA")
        data.energy = 420
        data.color = color("FFB15A")
        data.shape = "DISK"
        data.size = 7
        obj = bpy.data.objects.new("SY_StreetWash", data)
        env.objects.link(obj)
        obj.location = (x, 18, 6.2)
    point_light(scene, "SY_StageLight", (140, -19, 5), 280, 2.4)
    point_light(scene, "SY_BoatLight", (55, -4, 3), 150, 1.8)
    cameras = {
        "Camera_Entrance": ((4, 5, 8.0), (34, 19, 3.3), 30),
        "Camera_Bridge": ((75, -27, 12.0), (95, 4, 5.0), 29),
        "Camera_Quay": ((111, -14, 6.2), (128, 8, 2.5), 32),
    }
    for name, (loc, target, lens) in cameras.items():
        data = bpy.data.cameras.new(name)
        data.lens = lens
        data.clip_end = 500
        obj = bpy.data.objects.new(name, data)
        env.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = bpy.data.objects["Camera_Entrance"]
    scene.render.engine = "CYCLES"  # replaced by Eevee in sy_render.py; master stays portable
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"


def build_greybox(scene):
    p = palette()
    for resource_id in RESOURCE_IDS:
        b = Builder()
        if resource_id == "model-riverbanks":
            b.box(p["stone"], (180, 27, 1.2), (0, 25.5, 0))
            b.box(p["stone"], (180, 27, 1.2), (0, -25.5, 0))
        elif resource_id == "model-water":
            b.box(p["water"], (180, 24, 0.04), (0, 0, 0), bevel=0)
        elif resource_id == "model-bridge":
            b.box(p["stone"], (6.2, 30, 0.35), (0, 0, 3.3))
        elif resource_id == "model-lantern-tower":
            for w, z, h in ((12, 0.3, 0.6), (9, 2.6, 4), (7.4, 6.6, 3.2), (5.8, 10.4, 3.0)):
                b.box(p["stone"] if z < 1 else p["plaster"], (w, w, h), (0, 0, z))
            hip_roof(b, p, 8, 8, 12.3, 2.5)
        elif resource_id.startswith("model-shop"):
            i = int(resource_id[-2:])
            w = 12 if i == 6 else 8.5
            h = 7 if i in (2, 4, 6) else 4
            b.box(p["plaster"], (w, 7, h), (0, 0, h / 2))
            gable_roof(b, p, w + 1, 8, h, 1.4)
        elif resource_id == "model-paifang":
            for x in (-4.5, 4.5):
                b.box(p["red"], (0.5, 0.5, 5.5), (x, 0, 2.75))
            b.box(p["dark"], (10, 0.5, 0.5), (0, 0, 4.5))
        elif resource_id.startswith("model-lantern-array"):
            for y in (-13, 13):
                b.box(p["dark"], (0.2, 0.2, 5), (0, y, 2.8))
            b.beam(p["dark"], (0, -13, 5.3), (0, 13, 5.3), 0.03)
        elif resource_id in ("model-boat", "model-skiff"):
            b.box(p["wood"], (11 if resource_id == "model-boat" else 5.5, 3.4 if resource_id == "model-boat" else 1.8, 0.7), (0, 0, 0.35))
        elif resource_id == "model-performance":
            b.box(p["wood"], (11, 7.5, 1), (0, 0, 0.5))
        elif resource_id == "model-quay":
            b.box(p["stone"], (8.5, 8, 0.5), (0, -1, 0.25))
        elif resource_id.startswith("model-stall"):
            b.box(p["wood"], (4.5, 3, 2.8), (0, 0, 1.4))
        else:
            b.blob(p["lantern"], 0.6, (0, 0, 0.3))
        build_resource(scene, resource_id, b)
    setup_environment(scene)


def load_chinese_font():
    candidates = [Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simsun.ttc"),
                  Path("C:/Windows/Fonts/simhei.ttf")]
    for path in candidates:
        if path.exists():
            try:
                return bpy.data.fonts.load(str(path)), str(path), None
            except Exception as exc:
                return None, str(path), repr(exc)
    return None, None, "No supported Chinese font found in C:/Windows/Fonts"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--greybox", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args(argv)
    scene = own_scene()
    clean_owned(scene)
    font, font_path, font_error = (None, None, "Greybox labels intentionally omitted") if args.greybox else load_chinese_font()
    if args.greybox:
        build_greybox(scene)
        save_path = ARTIFACTS / "greybox-source.blend"
    else:
        p = palette()
        build_riverbanks(scene, p)
        build_water(scene, p)
        build_paifang(scene, p, font)
        build_bridge(scene, p)
        build_tower(scene, p, font)
        for i in range(1, 7):
            build_shop(scene, p, font, i)
        build_stall(scene, p, font, "riddle")
        build_stall(scene, p, font, "tea")
        for i in range(1, 5):
            build_lantern_array(scene, p, i)
        build_lotus(scene, p)
        build_paperboat(scene, p)
        build_fish(scene, p)
        build_boat(scene, p)
        build_skiff(scene, p)
        build_performance(scene, p)
        build_quay(scene, p)
        setup_environment(scene)
        save_path = BLEND_PATH
    scene["project"] = "上元灯夜 / Shangyuan Lantern Night"
    scene["greybox"] = args.greybox
    scene["route_length_m"] = 260
    scene["baked"] = 0
    for script_path in Path(__file__).parent.glob("sy_*.py"):
        text = bpy.data.texts.get(script_path.name) or bpy.data.texts.new(script_path.name)
        text.from_string(script_path.read_text(encoding="utf-8"))
    bpy.context.view_layer.update()
    for path in (ARTIFACTS, ARTIFACTS / "validation"): 
        path.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(save_path))
    report = {"mode": "greybox" if args.greybox else "full", "blend": str(save_path),
              "resources": len(RESOURCE_IDS), "font_path": font_path, "font_error": font_error,
              "materials": len([m for m in bpy.data.materials if m.name.startswith("SY_")]),
              "gi_bake": False}
    (ARTIFACTS / "validation" / ("greybox-build.json" if args.greybox else "build-log.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SY_BUILD_OK", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
