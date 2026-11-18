"""Export each Shangyuan resource collection as an independent realtime GLB.

blender -b assets/blender/shangyuan-lantern-night.blend --python sy_export.py
blender -b artifacts/shangyuan/greybox-source.blend --python sy_export.py -- --greybox
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "shangyuan"
PREFIX = "SYR_"


def resource_collections(scene):
    return sorted((c for c in scene.collection.children if c.name.startswith(PREFIX)), key=lambda c: c.name)


def export_glb(scene, objects, path):
    for other in bpy.data.objects:
        other.select_set(False)
    bpy.context.view_layer.update()
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = next((o for o in objects if o.type == "MESH"), objects[0])
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", export_extras=True, export_apply=True,
        export_yup=True, export_lights=False, export_cameras=False, export_materials="EXPORT",
        export_animations=False, use_selection=True, use_active_scene=True,
    )


def local_mesh_stats(collection):
    roots = [o for o in collection.all_objects if o.type == "MESH" and o.parent is None]
    if not roots:
        return [0, 0, 0], 0, [], []
    root = next((o for o in roots if o.get("resource_id")), roots[0])
    inverse = root.matrix_world.inverted()
    points = []
    triangles = 0
    materials = set()
    pivots = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in collection.all_objects:
        if obj.type == "EMPTY" and obj.get("dynamic"):
            pivots.append({"name": obj.name, "pivot": obj.get("pivot", "dynamic"), "axis": obj.get("axis", "Z")})
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        triangles += len(mesh.loop_triangles)
        materials.update(m.name for m in mesh.materials if m)
        transform = inverse @ obj.matrix_world
        points.extend(transform @ v.co for v in mesh.vertices)
        evaluated.to_mesh_clear()
    if not points:
        return [0, 0, 0], triangles, sorted(materials), pivots
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    return [round(high[i] - low[i], 3) for i in range(3)], triangles, sorted(materials), pivots


def greybox(scene):
    objects = [o for c in resource_collections(scene) for o in c.all_objects if o.type in {"MESH", "EMPTY"}]
    path = OUT / "greybox.glb"
    export_glb(scene, objects, path)
    print("SY_GREYBOX_EXPORT_OK", path, path.stat().st_size)


def full(scene):
    model_dir = OUT / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for collection in resource_collections(scene):
        resource_id = collection["resource_id"]
        objects = [o for o in collection.all_objects if o.type in {"MESH", "EMPTY"}]
        roots = [o for o in objects if o.parent is None]
        origin = Vector(collection["origin"])
        saved = {o.name: o.location.copy() for o in roots}
        # Export around the resource pivot; restore the assembled master afterwards.
        for obj in roots:
            obj.location -= origin
        bpy.context.view_layer.update()
        path = model_dir / f"{resource_id}.glb"
        export_glb(scene, objects, path)
        for obj in roots:
            obj.location = saved[obj.name]
        bpy.context.view_layer.update()
        dimensions, triangles, materials, pivots = local_mesh_stats(collection)
        root = next((o for o in roots if o.get("resource_id") == resource_id), None)
        rotation = root.rotation_euler.z if root else 0
        entry = {
            "id": resource_id,
            "file": f"models/{resource_id}.glb",
            "collection": collection.name,
            "position_blender": list(origin),
            "position_yup": [origin.x, origin.z, -origin.y],
            "rotation_z_blender": rotation,
            "rotation_y_yup": rotation,
            "dimensions_local_m": dimensions,
            "triangles": triangles,
            "materials": materials,
            "dynamic_pivots": pivots,
            "bytes": path.stat().st_size,
            "collision": root.get("collision", "simple convex/box proxies recommended") if root else "",
        }
        if root and root.get("interaction"):
            entry["interaction"] = root["interaction"]
        if root and root.get("water_origin"):
            entry["origin_note"] = root["water_origin"]
        entries.append(entry)
        print("SY_EXPORTED", resource_id, triangles, path.stat().st_size)
    layout = {
        "title": "上元灯夜 / Shangyuan Lantern Night",
        "version": 1,
        "units": "meters",
        "source_axes": "Blender Z-up; river along X; north +Y",
        "export_axes": "glTF Y-up; game=(x,z,-y)",
        "baked": False,
        "water": {"id": "model-water", "realtime": True, "extent_blender": {"x": [0, 180], "y": [-12, 12], "z": 0}},
        "route": {"length_m_approx": 260, "street_width_m": 6,
                  "waypoints_blender": [[10, 18, 0.65], [20, 18, 0.65], [90, 18, 0.65], [90, -18, 0.65], [140, -18, 0.65], [125, 5, 0.25]]},
        "spawn": {"id": "spawn-entrance", "position_blender": [10, 18, 1.45], "forward_blender": [1, 0, 0]},
        "photo_spots": [
            {"id": "entrance", "position_blender": [12, 18, 2.1], "target_blender": [25, 18, 3.8]},
            {"id": "bridge-top", "position_blender": [90, 0, 4.85], "target_blender": [98, 23, 8]},
            {"id": "quay", "position_blender": [125, 5, 1.7], "target_blender": [98, 23, 8]},
        ],
        "triggers": [
            {"id": "riddle", "resource": "model-stall-riddle", "position_blender": [67, 15, 1.3], "radius_m": 2.5},
            {"id": "tea-rest", "resource": "model-stall-tea", "position_blender": [133, 21, 1.3], "radius_m": 2.5},
            {"id": "release-lantern", "resource": "model-quay", "position_blender": [125, 5, 0.8], "radius_m": 3.0},
            {"id": "performance", "resource": "model-performance", "position_blender": [140, -17, 1.5], "radius_m": 6.0},
            {"id": "boat-boarding", "resource": "model-boat", "position_blender": [55, -4, 0.8], "radius_m": 4.0},
        ],
        "resources": entries,
    }
    (OUT / "layout.json").write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SY_EXPORT_OK", len(entries), OUT)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--greybox", action="store_true")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    if args.greybox:
        greybox(scene)
    else:
        full(scene)


if __name__ == "__main__":
    main()
