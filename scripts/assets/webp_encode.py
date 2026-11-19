"""Re-encode PNG textures as lossy WebP with alpha, for the glTF optimizer."""

import json
import sys

from PIL import Image

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
quality = int(sys.argv[2]) if len(sys.argv) > 2 else 90

for job in manifest:
    image = Image.open(job["input"]).convert("RGBA")
    image.save(
        job["output"],
        "WEBP",
        quality=quality,
        method=6,
        alpha_quality=100,
    )
