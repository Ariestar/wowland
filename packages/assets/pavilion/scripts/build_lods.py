"""Generate LOD1 / LOD2 for SM_Env_Pavilion_Hex_01.

Run:
    blender -b assets/pavilion/exports/SM_Env_Pavilion_Hex_01.blend \
        --python assets/pavilion/scripts/build_lods.py

Outputs:
    exports/SM_Env_Pavilion_Hex_01_LODs.blend
    exports/SM_Env_Pavilion_Hex_01_LOD1.glb / .fbx
    exports/SM_Env_Pavilion_Hex_01_LOD2.glb / .fbx
    reports/lod_report.json
"""

import bpy
import bmesh
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.dirname(HERE)
EXPORT_DIR = os.path.join(ASSET_DIR, "exports")
REPORT_DIR = os.path.join(ASSET_DIR, "reports")

SOURCE = "SM_Env_Pavilion_Hex_01"
RATIOS = [("LOD1", 0.45), ("LOD2", 0.20)]


def tris(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    mesh = ev.to_mesh()
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    ev.to_mesh_clear()
    return count


def topology(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
    bm.free()
    return boundary, non_manifold


def clean_decimated(obj):
    """Drop the double-sided triangle fins Decimate can leave behind.

    Decimate occasionally outputs pairs of coincident triangles with their own
    vertices. Blender's mesh validation removes one face of each pair, leaving a
    loose triangle. Deleting all fully boundary triangles keeps the shell watertight.
    """
    obj.data.validate(verbose=False, clean_customdata=False)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    fins = [f for f in bm.faces if len(f.verts) == 3 and all(e.is_boundary for e in f.edges)]
    if fins:
        bmesh.ops.delete(bm, geom=fins, context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(fins)


source = bpy.data.objects.get(SOURCE)
if source is None:
    raise RuntimeError(f"missing source object: {SOURCE}")

col = bpy.data.collections.get("COL_LODs")
if col is None:
    col = bpy.data.collections.new("COL_LODs")
    bpy.context.scene.collection.children.link(col)

# Phase 1: build all LOD meshes before any export touches the scene.
lods = []
for name, ratio in RATIOS:
    full_name = f"{SOURCE}_{name}"
    old = bpy.data.objects.get(full_name)
    if old:
        data = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)

    lod = source.copy()
    lod.data = source.data.copy()
    lod.name = lod.data.name = full_name
    lod.hide_render = True
    col.objects.link(lod)

    bpy.ops.object.select_all(action="DESELECT")
    lod.select_set(True)
    bpy.context.view_layer.objects.active = lod

    dec = lod.modifiers.new("LOD_Decimate", "DECIMATE")
    dec.decimate_type = "COLLAPSE"
    dec.ratio = ratio
    dec.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=dec.name)

    fins = clean_decimated(lod)
    tri_count = tris(lod)
    boundary, non_manifold = topology(lod)
    print(f"[LOD] {full_name}: {tri_count} tris, {len(lod.data.vertices)} verts, "
          f"{boundary} boundary, {non_manifold} non-manifold, {fins} fins removed")
    lods.append((name, ratio, lod, tri_count, boundary, non_manifold))

# Phase 2: export each LOD and record evidence.
report = {"source": SOURCE, "lod0_tris": tris(source), "lods": []}
for name, ratio, lod, tri_count, boundary, non_manifold in lods:
    full_name = lod.name
    bpy.ops.object.select_all(action="DESELECT")
    lod.select_set(True)
    bpy.context.view_layer.objects.active = lod

    glb_path = os.path.join(EXPORT_DIR, f"{full_name}.glb")
    fbx_path = os.path.join(EXPORT_DIR, f"{full_name}.fbx")
    bpy.ops.export_scene.gltf(
        filepath=glb_path, export_format="GLB", use_selection=True,
        export_apply=True, export_yup=True, export_materials="EXPORT",
        export_texcoords=True, export_normals=True, export_cameras=False,
        export_lights=False)
    bpy.ops.export_scene.fbx(
        filepath=fbx_path, use_selection=True, object_types={"MESH"},
        apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
        apply_unit_scale=True, bake_anim=False, path_mode="AUTO")

    report["lods"].append({
        "name": full_name,
        "ratio": ratio,
        "triangles": tri_count,
        "boundary_edges": boundary,
        "non_manifold_edges": non_manifold,
        "glb": glb_path,
        "fbx": fbx_path,
    })

bpy.ops.object.select_all(action="DESELECT")
source.select_set(True)
bpy.context.view_layer.objects.active = source
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(
    EXPORT_DIR, "SM_Env_Pavilion_Hex_01_LODs.blend"))

with open(os.path.join(REPORT_DIR, "lod_report.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
