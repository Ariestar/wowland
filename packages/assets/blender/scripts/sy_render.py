"""Render three Eevee night previews from the unbaked Shangyuan master."""
import json
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts/shangyuan/preview"
CAMERAS = [("Camera_Entrance", "01-entrance.png"), ("Camera_Bridge", "02-bridge.png"), ("Camera_Quay", "03-quay.png")]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 64
        if hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = True
    records = []
    for camera_name, filename in CAMERAS:
        scene.camera = bpy.data.objects[camera_name]
        path = OUT / filename
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        records.append({"camera": camera_name, "path": str(path), "bytes": path.stat().st_size,
                        "resolution": [1280, 720], "engine": "Eevee"})
        print("SY_RENDER_OK", filename, path.stat().st_size)
    (ROOT / "artifacts/shangyuan/validation/render-log.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
