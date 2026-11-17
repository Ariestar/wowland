"""Validate Shangyuan resource bounds, pivots, materials, triangles and exported files."""
import json
import math
import struct
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts/shangyuan"
PREFIX = "SYR_"
REQUIRED = {
    "model-riverbanks", "model-paifang", "model-bridge", "model-lantern-tower",
    *{f"model-shop-{i:02d}" for i in range(1, 7)}, "model-stall-riddle", "model-stall-tea",
    *{f"model-lantern-array-s{i}" for i in range(1, 5)},
    "model-river-lantern-lotus", "model-river-lantern-paperboat", "model-river-lantern-fish",
    "model-boat", "model-skiff", "model-performance", "model-quay", "model-water",
}


def inspect(collection):
    objects = list(collection.all_objects)
    root = next((o for o in objects if o.type == "MESH" and o.get("resource_id")), None)
    inverse = root.matrix_world.inverted() if root else None
    points = []
    triangles = 0
    missing = []
    materials = set()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        triangles += len(mesh.loop_triangles)
        if not mesh.materials or any(polygon.material_index >= len(mesh.materials) for polygon in mesh.polygons):
            missing.append(obj.name)
        materials.update(m.name for m in mesh.materials if m)
        if inverse:
            matrix = inverse @ obj.matrix_world
            points.extend(matrix @ v.co for v in mesh.vertices)
        evaluated.to_mesh_clear()
    low = [min(p[i] for p in points) for i in range(3)] if points else [0, 0, 0]
    high = [max(p[i] for p in points) for i in range(3)] if points else [0, 0, 0]
    dimensions = [high[i] - low[i] for i in range(3)]
    origin = Vector(collection.get("origin", (0, 0, 0)))
    origin_error = (root.location - origin).length if root else math.inf
    scale_error = max(abs(s - 1) for o in objects for s in o.scale) if objects else math.inf
    return {
        "objects": len(objects),
        "mesh_objects": sum(o.type == "MESH" for o in objects),
        "triangles": triangles,
        "dimensions_local_m": [round(v, 3) for v in dimensions],
        "bounds_local_m": {"min": [round(v, 3) for v in low], "max": [round(v, 3) for v in high]},
        "materials": sorted(materials),
        "missing_materials": missing,
        "origin_error_m": round(origin_error, 6),
        "non_unit_scale_max_error": round(scale_error, 6),
        "dynamic_pivots": [o.name for o in objects if o.type == "EMPTY" and o.get("dynamic")],
    }


def glb_info(path):
    if not path.exists():
        return {"exists": False}
    with path.open("rb") as handle:
        header = handle.read(12)
    valid = len(header) == 12 and header[:4] == b"glTF" and struct.unpack("<I", header[4:8])[0] == 2
    return {"exists": True, "bytes": path.stat().st_size, "valid_glb_header": valid}


def main():
    scene = bpy.context.scene
    collections = {c.get("resource_id"): c for c in scene.collection.children if c.name.startswith(PREFIX)}
    resources = {resource_id: inspect(c) for resource_id, c in sorted(collections.items())}
    total_triangles = sum(r["triangles"] for r in resources.values())
    materials = sorted({m for r in resources.values() for m in r["materials"]})
    errors = []
    for resource_id in sorted(REQUIRED - set(collections)):
        errors.append(f"missing resource: {resource_id}")
    for resource_id, stats in resources.items():
        if stats["missing_materials"]:
            errors.append(f"{resource_id}: missing materials")
        if stats["origin_error_m"] > 0.001:
            errors.append(f"{resource_id}: root does not match collection origin")
        if stats["non_unit_scale_max_error"] > 0.001:
            errors.append(f"{resource_id}: unapplied scale")
    if total_triangles > 250000:
        errors.append(f"triangle budget exceeded: {total_triangles}")
    if len(materials) > 12:
        errors.append(f"material budget exceeded: {len(materials)}")
    if "model-water" in resources:
        dims = resources["model-water"]["dimensions_local_m"]
        if abs(dims[0] - 180) > 0.1 or abs(dims[1] - 24) > 0.1:
            errors.append(f"water extent incorrect: {dims}")
    if "model-bridge" in resources:
        dims = resources["model-bridge"]["dimensions_local_m"]
        if not (29 <= dims[1] <= 31 and dims[2] >= 4):
            errors.append(f"bridge bounds incorrect: {dims}")
    if "model-lantern-tower" in resources:
        dims = resources["model-lantern-tower"]["dimensions_local_m"]
        if not (14.5 <= dims[2] <= 16.5):
            errors.append(f"tower height incorrect: {dims[2]}")
    exports = {}
    if not scene.get("greybox", False):
        for resource_id in collections:
            exports[resource_id] = glb_info(OUT / "models" / f"{resource_id}.glb")
            if not exports[resource_id].get("valid_glb_header"):
                errors.append(f"invalid or missing GLB: {resource_id}")
        exports["greybox"] = glb_info(OUT / "greybox.glb")
        if not exports["greybox"].get("valid_glb_header"):
            errors.append("invalid or missing greybox.glb")
    report = {
        "project": "上元灯夜 / Shangyuan Lantern Night",
        "blend": bpy.data.filepath,
        "passed": not errors,
        "errors": errors,
        "totals": {"resources": len(resources), "objects": sum(r["objects"] for r in resources.values()),
                   "mesh_objects": sum(r["mesh_objects"] for r in resources.values()),
                   "triangles": total_triangles, "materials": len(materials), "triangle_budget": 250000,
                   "material_budget": 12, "gi_baked": False},
        "material_names": materials,
        "resources": resources,
        "exports": exports,
    }
    (OUT / "validation").mkdir(parents=True, exist_ok=True)
    path = OUT / "validation/model-stats.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SY_VALIDATION", "PASS" if not errors else "FAIL", json.dumps(report["totals"], ensure_ascii=False))
    for error in errors:
        print("SY_VALIDATION_ERROR", error)
    if errors:
        raise RuntimeError("Shangyuan validation failed; see model-stats.json")


if __name__ == "__main__":
    main()
