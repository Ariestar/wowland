"""Generate tileable PBR detail maps for the Shangyuan runtime materials.

This is the texture-authoring stage that sits between `sy_build.py` and
`sy_materialize.py`. It produces small, seamless base-colour and normal maps so
the GLBs can keep full PBR shading without shipping the offline lookdev shaders.

Run:
    python packages/assets/blender/scripts/sy_generate_textures.py

Outputs:
    packages/assets/blender/textures/T_SY_<Material>_BaseColor.jpg
    packages/assets/blender/textures/T_SY_<Material>_Normal.jpg
    packages/assets/blender/textures/manifest.json
"""

import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "textures"

MATERIALS = {
    "Stone": {"color": "#747984", "pattern": "stone", "normal": 1.15},
    "Plaster": {"color": "#A89E89", "pattern": "plaster", "normal": 0.55},
    "Wood": {"color": "#865137", "pattern": "wood", "normal": 0.8},
    "DarkWood": {"color": "#382A2B", "pattern": "darkwood", "normal": 0.65},
    "Roof": {"color": "#496A7E", "pattern": "roof", "normal": 1.0},
    "Vermilion": {"color": "#A33B30", "pattern": "paint", "normal": 0.45},
    "Gold": {"color": "#D1A255", "pattern": "metal", "normal": 0.35},
    "Paper": {"color": "#E2B573", "pattern": "paper", "normal": 0.3},
    "Lantern": {"color": "#FFD18A", "pattern": "lantern", "normal": 0.4},
    "Foliage": {"color": "#314C48", "pattern": "foliage", "normal": 0.7},
}


def rgb(hex_value):
    value = hex_value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def smoothstep(t):
    return t * t * (3.0 - 2.0 * t)


def lattice(ix, iy, period, seed):
    """Deterministic value hash with a wrapping lattice for seamless tiles."""
    ix %= period
    iy %= period
    n = (ix * 374761393 + iy * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFFFFFF) / 4294967295.0


def value_noise(x, y, period, seed):
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    fx, fy = smoothstep(fx), smoothstep(fy)
    a = lattice(x0, y0, period, seed)
    b = lattice(x0 + 1, y0, period, seed)
    c = lattice(x0, y0 + 1, period, seed)
    d = lattice(x0 + 1, y0 + 1, period, seed)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(u, v, base_period, seed, octaves=4):
    value = 0.0
    amplitude = 0.5
    total = 0.0
    period = base_period
    for octave in range(octaves):
        value += amplitude * value_noise(u * period, v * period, period, seed + octave * 17)
        total += amplitude
        period *= 2
        amplitude *= 0.5
    return value / total


def height_for(pattern, u, v, seed):
    if pattern == "stone":
        base = fbm(u, v, 5, seed, 5)
        cracks = 1.0 - abs(math.sin((u * 6.0 + fbm(u, v, 7, seed + 2, 2) * 5.0) * math.pi))
        return base * 0.7 + cracks * 0.3
    if pattern == "plaster":
        return fbm(u, v, 7, seed, 5) * 0.65 + fbm(u, v, 31, seed + 4, 2) * 0.35
    if pattern == "wood":
        grain = math.sin((v * 28.0 + fbm(u, v, 4, seed, 3) * 7.0) * math.pi)
        return 0.55 + grain * 0.25 + fbm(u, v, 18, seed + 8, 3) * 0.2
    if pattern == "darkwood":
        grain = math.sin((v * 38.0 + fbm(u, v, 5, seed, 3) * 9.0) * math.pi)
        return 0.55 + grain * 0.28 + fbm(u, v, 24, seed + 9, 2) * 0.17
    if pattern == "roof":
        rows = math.sin(v * 18.0 * math.pi) * 0.5 + 0.5
        seams = math.sin(u * 12.0 * math.pi) * 0.5 + 0.5
        return rows * 0.45 + seams * 0.3 + fbm(u, v, 16, seed, 3) * 0.25
    if pattern == "paint":
        return fbm(u, v, 9, seed, 4) * 0.75 + fbm(u, v, 36, seed + 3, 2) * 0.25
    if pattern == "metal":
        return fbm(u, v, 12, seed, 4) * 0.7 + fbm(u, v, 42, seed + 6, 2) * 0.3
    if pattern == "paper":
        fibers = abs(math.sin((u * 17.0 + v * 23.0 + fbm(u, v, 5, seed, 3) * 4.0) * math.pi))
        return fibers * 0.35 + fbm(u, v, 18, seed + 5, 3) * 0.65
    if pattern == "lantern":
        ribs = abs(math.sin(u * 10.0 * math.pi)) ** 2
        return ribs * 0.45 + fbm(u, v, 14, seed, 3) * 0.55
    if pattern == "foliage":
        return fbm(u, v, 9, seed, 5) * 0.8 + fbm(u, v, 32, seed + 1, 2) * 0.2
    return fbm(u, v, 8, seed, 4)


def shade(pattern, u, v, base, seed):
    base_r, base_g, base_b = base
    if pattern == "stone":
        n = fbm(u, v, 6, seed, 4)
        mottling = 0.72 + n * 0.5
        cool = 0.93 + fbm(u, v, 21, seed + 4, 2) * 0.12
        return (
            base_r * mottling * cool,
            base_g * mottling * cool,
            base_b * mottling * (0.96 + n * 0.1),
        )
    if pattern == "plaster":
        n = fbm(u, v, 9, seed, 4)
        stain = fbm(u, v, 3, seed + 4, 2)
        return (
            base_r * (0.78 + n * 0.3 + stain * 0.12),
            base_g * (0.76 + n * 0.3 + stain * 0.1),
            base_b * (0.72 + n * 0.3 + stain * 0.08),
        )
    if pattern in {"wood", "darkwood"}:
        grain = math.sin((v * (26.0 if pattern == "wood" else 36.0) + fbm(u, v, 4, seed, 3) * 8.0) * math.pi)
        n = fbm(u, v, 20, seed + 2, 3)
        value = 0.78 + grain * 0.18 + n * 0.12
        warm = 1.0 + grain * 0.06
        return (base_r * value * warm, base_g * value * 0.98, base_b * value * 0.94)
    if pattern == "roof":
        rows = math.sin(v * 18.0 * math.pi) * 0.5 + 0.5
        seams = math.sin(u * 12.0 * math.pi) * 0.5 + 0.5
        n = fbm(u, v, 15, seed + 1, 3)
        value = 0.72 + rows * 0.2 + seams * 0.08 + n * 0.1
        return (base_r * value * 0.96, base_g * value, base_b * value * 1.06)
    if pattern == "paint":
        n = fbm(u, v, 10, seed, 4)
        wear = 0.82 + n * 0.24
        return (base_r * wear, base_g * wear * 0.96, base_b * wear * 0.92)
    if pattern == "metal":
        n = fbm(u, v, 12, seed, 4)
        value = 0.7 + n * 0.48
        return (base_r * value, base_g * value, base_b * value * 0.94)
    if pattern in {"paper", "lantern"}:
        fiber = abs(math.sin((u * 17.0 + v * 23.0 + fbm(u, v, 5, seed, 3) * 4.0) * math.pi))
        n = fbm(u, v, 19, seed + 2, 3)
        value = 0.82 + fiber * 0.12 + n * 0.12
        if pattern == "lantern":
            value += abs(math.sin(u * 10.0 * math.pi)) * 0.08
        return (base_r * value, base_g * value * 0.97, base_b * value * 0.9)
    if pattern == "foliage":
        n = fbm(u, v, 9, seed, 5)
        leaf = fbm(u, v, 28, seed + 1, 2)
        return (base_r * (0.72 + n * 0.36), base_g * (0.76 + leaf * 0.3), base_b * (0.72 + n * 0.3))
    return (base_r, base_g, base_b)


def normal_pixel(pattern, u, v, seed, strength, step):
    dx = height_for(pattern, (u + step) % 1.0, v, seed) - height_for(pattern, (u - step) % 1.0, v, seed)
    dy = height_for(pattern, u, (v + step) % 1.0, seed) - height_for(pattern, u, (v - step) % 1.0, seed)
    nx, ny, nz = -dx * strength, -dy * strength, 1.0
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (
        int((nx / length * 0.5 + 0.5) * 255),
        int((ny / length * 0.5 + 0.5) * 255),
        int((nz / length * 0.5 + 0.5) * 255),
    )


def write_maps(name, spec, size, out_dir):
    seed = sum(ord(c) for c in name)
    base = rgb(spec["color"])
    pattern = spec["pattern"]
    base_pixels = []
    normal_pixels = []
    for y in range(size):
        v = (y + 0.5) / size
        for x in range(size):
            u = (x + 0.5) / size
            base_pixels.append(tuple(max(0, min(255, int(c))) for c in shade(pattern, u, v, base, seed)))
            normal_pixels.append(normal_pixel(pattern, u, v, seed, spec["normal"], 1.0 / size))

    stem = f"T_SY_{name}"
    base_path = out_dir / f"{stem}_BaseColor.jpg"
    normal_path = out_dir / f"{stem}_Normal.jpg"
    base_image = Image.new("RGB", (size, size))
    base_image.putdata(base_pixels)
    base_image.save(base_path, quality=88, subsampling=0)
    normal_image = Image.new("RGB", (size, size))
    normal_image.putdata(normal_pixels)
    normal_image.save(normal_path, quality=90, subsampling=0)
    return base_path, normal_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {"size": args.size, "materials": {}}
    for name, spec in MATERIALS.items():
        base_path, normal_path = write_maps(name, spec, args.size, args.out)
        manifest["materials"][name] = {
            "base_color": str(base_path.relative_to(ROOT)).replace("\\", "/"),
            "normal": str(normal_path.relative_to(ROOT)).replace("\\", "/"),
            "pattern": spec["pattern"],
        }
        print("TEXTURE", name, base_path.name, normal_path.name)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("TEXTURES_OK", len(manifest["materials"]), args.out)


if __name__ == "__main__":
    main()
