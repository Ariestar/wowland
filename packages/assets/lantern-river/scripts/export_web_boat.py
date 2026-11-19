"""Export the pleasure boat with the same full PBR maps as the world.

    blender -b exports/SM_Scene_LanternRiver_Night.blend --python scripts/export_web_boat.py

The runtime clones this GLB along the river, so it needs its own baked maps.
The world export already owns the street; this keeps the boat from falling back
to the flat kit materials whenever it is near the camera.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "web" / "boat.glb"
sys.path.insert(0, str(Path(__file__).parent))
from export_web_world import add_detail_uv, dedupe_materials, wire_pbr_textures  # noqa: E402


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--draco", action="store_true")
    args = parser.parse_args(argv)

    boat = bpy.data.objects.get("PROP_Boat_01")
    if boat is None:
        raise RuntimeError("PROP_Boat_01 not found in the lookdev scene")

    wire_pbr_textures()

    # The three lookdev boats share one kit mesh.  Make this export independent
    # before transforms and per-object material overrides are applied.
    boat.data = boat.data.copy()

    bpy.ops.object.select_all(action="DESELECT")
    boat.hide_set(False)
    boat.hide_viewport = False
    boat.select_set(True)
    bpy.context.view_layer.objects.active = boat

    # Runtime positions the boat; keep the exported hull centred at the origin.
    boat.location = (0.0, 0.0, 0.0)
    boat.rotation_euler = (0.0, 0.0, 0.0)
    boat.scale = (1.0, 1.0, 1.0)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    add_detail_uv(boat)
    dedupe_materials(boat)

    boat.data.calc_loop_triangles()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(out),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_texcoords=True,
        export_normals=True,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_draco_mesh_compression_enable=args.draco,
        export_draco_mesh_compression_level=6,
        export_draco_position_quantization=14,
        export_draco_normal_quantization=10,
        export_draco_texcoord_quantization=12,
    )
    print(
        "LR_WEB_BOAT_OK",
        {
            "triangles": len(boat.data.loop_triangles),
            "materials": len(boat.data.materials),
            "bytes": out.stat().st_size,
            "path": str(out),
        },
    )


if __name__ == "__main__":
    main()
