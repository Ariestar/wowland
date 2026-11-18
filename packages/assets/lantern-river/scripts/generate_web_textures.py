"""Generate tileable PBR detail maps for the Lantern River kit materials.

The lookdev scene's materials are Principled BSDFs with procedural bump.  glTF
cannot carry those node graphs, so the web export wires these seamless maps into
the same materials before writing the GLB: base colour is tinted per material,
normal and roughness maps restore the surface detail the offline bump provided.

Maps are authored at a world-scale UV density: the exporter projects a second
UV set across the merged world mesh at DETAIL_TILE_METERS per texture repeat.

    python packages/assets/lantern-river/scripts/generate_web_textures.py
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "textures"

# The tint is baked into the texture: glTF's baseColorFactor cannot carry a
# Blender multiply node, so the export wires these maps straight into Base Color.
MATERIALS = {
    # Large architectural surfaces: 512 px, ~2.4 m per repeat.
    "MAT_SCENE_Paving": {"color": "#55535F", "pattern": "paving", "normal": 0.45, "roughness": 0.64, "size": 512},
    "MAT_SCENE_QuayStone": {"color": "#4C4954", "pattern": "stone", "normal": 0.35, "roughness": 0.80, "size": 512},
    "MAT_LR_Stone": {"color": "#5A5762", "pattern": "stone", "normal": 0.35, "roughness": 0.78, "size": 512},
    "MAT_LR_Stone_Light": {"color": "#7E7B74", "pattern": "stone", "normal": 0.3, "roughness": 0.74, "size": 512},
    "MAT_LR_Plaster_Warm": {"color": "#E8DFCC", "pattern": "plaster", "normal": 0.04, "roughness": 0.72, "size": 512},
    "MAT_LR_Plaster_Sand": {"color": "#D8CDB8", "pattern": "plaster", "normal": 0.04, "roughness": 0.75, "size": 512},
    "MAT_LR_Wood_Dark": {"color": "#33221C", "pattern": "wood_dark", "normal": 0.32, "roughness": 0.38, "size": 512},
    "MAT_LR_Wood_Warm": {"color": "#4A2F20", "pattern": "wood", "normal": 0.32, "roughness": 0.42, "size": 512},
    "MAT_LR_Roof_Tile": {"color": "#46545B", "pattern": "roof", "normal": 0.45, "roughness": 0.42, "size": 512},
    "MAT_LR_Roof_Blue": {"color": "#465A58", "pattern": "roof", "normal": 0.42, "roughness": 0.44, "size": 512},
    "MAT_LR_Lacquer_Red": {"color": "#A32E1B", "pattern": "lacquer", "normal": 0.12, "roughness": 0.40, "size": 512},
    # Small props and soft goods: 256 px keeps the atlas compact.
    "MAT_LR_Gold": {"color": "#D8B45A", "pattern": "metal", "normal": 0.1, "roughness": 0.28, "size": 256},
    "MAT_LR_Paper_Glow": {"color": "#FFD9A0", "pattern": "paper", "normal": 0.06, "roughness": 0.55, "size": 256},
    "MAT_LR_Paper_Red": {"color": "#FF6A3A", "pattern": "paper", "normal": 0.06, "roughness": 0.55, "size": 256},
    "MAT_LR_Cloth_Red": {"color": "#A8382E", "pattern": "cloth", "normal": 0.2, "roughness": 0.82, "size": 256},
    "MAT_LR_Cloth_Cream": {"color": "#E3D5B8", "pattern": "cloth", "normal": 0.2, "roughness": 0.85, "size": 256},
    "MAT_Pavilion_Wood": {"color": "#5A2A18", "pattern": "lacquer", "normal": 0.14, "roughness": 0.42, "size": 256},
    "MAT_Pavilion_Stone": {"color": "#3A4148", "pattern": "stone", "normal": 0.45, "roughness": 0.78, "size": 256},
    "MAT_Pavilion_Gold": {"color": "#D18A28", "pattern": "metal", "normal": 0.1, "roughness": 0.30, "size": 256},
    "MAT_Pavilion_Paint": {"color": "#1E4A50", "pattern": "lacquer", "normal": 0.12, "roughness": 0.44, "size": 256},
    "MAT_Pavilion_Roof": {"color": "#15202B", "pattern": "roof", "normal": 0.42, "roughness": 0.32, "size": 256},
    "MAT_Pavilion_Lantern": {"color": "#C81A10", "pattern": "paper", "normal": 0.06, "roughness": 0.55, "size": 128},
    "MAT_Lantern_Wood": {"color": "#2E160E", "pattern": "wood_dark", "normal": 0.3, "roughness": 0.42, "size": 128},
    "MAT_Lantern_Gold": {"color": "#D18A28", "pattern": "metal", "normal": 0.1, "roughness": 0.30, "size": 128},
    "MAT_Lantern_Paper": {"color": "#C81A10", "pattern": "paper", "normal": 0.06, "roughness": 0.55, "size": 128},
    "MAT_Lantern_Tassel": {"color": "#A8382E", "pattern": "cloth", "normal": 0.18, "roughness": 0.86, "size": 128},
    "MAT_SCENE_QuayLantern": {"color": "#D96A38", "pattern": "paper", "normal": 0.06, "roughness": 0.55, "size": 128},
    "MAT_SCENE_BoatPaper": {"color": "#FFE0AE", "pattern": "paper", "normal": 0.06, "roughness": 0.55, "size": 256},
    "MAT_SCENE_Trunk": {"color": "#2A1A18", "pattern": "bark", "normal": 0.5, "roughness": 0.70, "size": 256},
    "MAT_SCENE_Blossom": {"color": "#E894B8", "pattern": "blossom", "normal": 0.18, "roughness": 0.70, "size": 256},
}

# Duplicated kit materials share one map set.
ALIASES = {
    "MAT_Lantern_Wood.001": "MAT_Lantern_Wood",
    "MAT_Lantern_Gold.001": "MAT_Lantern_Gold",
    "MAT_Lantern_Paper.001": "MAT_Lantern_Paper",
    "MAT_Lantern_Tassel.001": "MAT_Lantern_Tassel",
}


def rgb(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def lattice(ix: int, iy: int, period: int, seed: int) -> float:
    ix %= period
    iy %= period
    n = (ix * 374761393 + iy * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFFFFFF) / 4294967295.0


def value_noise(x: float, y: float, period: int, seed: int) -> float:
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = smoothstep(x - x0), smoothstep(y - y0)
    a = lattice(x0, y0, period, seed)
    b = lattice(x0 + 1, y0, period, seed)
    c = lattice(x0, y0 + 1, period, seed)
    d = lattice(x0 + 1, y0 + 1, period, seed)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(u: float, v: float, base_period: int, seed: int, octaves: int = 4) -> float:
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


def mortar_height(u: float, v: float, cols: int, rows: int) -> float:
    """Rounded mortar grooves for brick and tile patterns, tileable in 0..1."""
    row = math.floor(v * rows)
    offset = 0.5 if row % 2 else 0.0
    uu = (u + offset / cols) % 1.0
    fu = (uu * cols) % 1.0
    fv = (v * rows) % 1.0
    edge_u = min(fu, 1.0 - fu)
    edge_v = min(fv, 1.0 - fv)
    edge = min(edge_u * cols, edge_v * rows)
    return min(1.0, max(0.0, edge / 0.09))


def height_for(pattern: str, u: float, v: float, seed: int) -> float:
    if pattern == "stone":
        base = fbm(u, v, 5, seed, 5)
        grain = fbm(u, v, 37, seed + 4, 2)
        pits = 1.0 - abs(fbm(u, v, 13, seed + 9, 3) * 2.0 - 1.0)
        return base * 0.62 + grain * 0.23 + pits * 0.15
    if pattern == "paving":
        brick = mortar_height(u, v, 4, 8)
        n = fbm(u, v, 19, seed + 2, 3)
        return 0.25 + brick * 0.55 + n * 0.2
    if pattern == "plaster":
        coarse = fbm(u, v, 6, seed, 5)
        fine = fbm(u, v, 43, seed + 4, 2)
        return coarse * 0.45 + fine * 0.55
    if pattern == "wood":
        warp = fbm(u, v, 4, seed, 3)
        grain = math.sin((v * 24.0 + warp * 6.0) * math.pi) * 0.5 + 0.5
        fine = fbm(u, v, 48, seed + 8, 2)
        return grain * 0.62 + fine * 0.38
    if pattern == "wood_dark":
        warp = fbm(u, v, 5, seed, 3)
        grain = math.sin((v * 34.0 + warp * 8.0) * math.pi) * 0.5 + 0.5
        fine = fbm(u, v, 52, seed + 9, 2)
        return grain * 0.66 + fine * 0.34
    if pattern == "roof":
        rows = math.sin(v * 16.0 * math.pi) * 0.5 + 0.5
        seams = math.sin(u * 8.0 * math.pi) * 0.5 + 0.5
        fine = fbm(u, v, 40, seed, 2)
        return rows * 0.5 + seams * 0.28 + fine * 0.22
    if pattern == "lacquer":
        orange_peel = fbm(u, v, 58, seed, 2)
        flow = fbm(u, v, 9, seed + 3, 3)
        return orange_peel * 0.65 + flow * 0.35
    if pattern == "metal":
        brush = math.sin(v * 90.0 * math.pi + fbm(u, v, 7, seed, 2) * 3.0) * 0.5 + 0.5
        fine = fbm(u, v, 46, seed + 4, 2)
        return brush * 0.5 + fine * 0.5
    if pattern == "paper":
        fiber = abs(math.sin((u * 13.0 + v * 19.0 + fbm(u, v, 6, seed, 3) * 4.0) * math.pi))
        fine = fbm(u, v, 55, seed + 5, 2)
        return fiber * 0.4 + fine * 0.6
    if pattern == "cloth":
        warp = math.sin(u * 46.0 * math.pi) * 0.5 + 0.5
        weft = math.sin(v * 46.0 * math.pi) * 0.5 + 0.5
        fine = fbm(u, v, 24, seed, 2)
        return warp * 0.35 + weft * 0.35 + fine * 0.3
    if pattern == "bark":
        ridges = math.sin(u * 34.0 * math.pi + fbm(u, v, 5, seed, 3) * 5.0) * 0.5 + 0.5
        coarse = fbm(u, v, 7, seed + 3, 3)
        return ridges * 0.62 + coarse * 0.38
    if pattern == "blossom":
        return fbm(u, v, 9, seed, 4)
    return fbm(u, v, 8, seed, 4)


def shade(pattern: str, u: float, v: float, base: tuple[int, int, int], seed: int):
    br, bg, bb = base
    if pattern == "stone":
        n = fbm(u, v, 6, seed, 4)
        stain = fbm(u, v, 2, seed + 6, 2)
        value = 0.92 + n * 0.1 + stain * 0.02
        return (br * value, bg * value * 0.99, bb * value * 1.02)
    if pattern == "paving":
        row = math.floor(v * 8.0)
        col = math.floor((u + (0.5 if row % 2 else 0.0) / 4.0) * 4.0)
        brick = lattice(int(col), int(row), 4, seed + 12) * 0.16 + 0.92
        n = fbm(u, v, 24, seed + 2, 3)
        joint = mortar_height(u, v, 4, 8)
        value = (0.84 + n * 0.16) * brick * (0.78 + joint * 0.22)
        return (br * value * 0.98, bg * value, bb * value * 1.05)
    if pattern == "plaster":
        n = fbm(u, v, 8, seed, 4)
        stain = fbm(u, v, 2, seed + 4, 3)
        streak = fbm(u * 6.0 % 1.0, v, 3, seed + 7, 2)
        value = 0.97 + n * 0.025 + stain * 0.015
        return (br * value, bg * value * 0.995, bb * value * 0.97)
    if pattern in {"wood", "wood_dark"}:
        rate = 22.0 if pattern == "wood" else 32.0
        warp = fbm(u, v, 4, seed, 3)
        grain = math.sin((v * rate + warp * 7.0) * math.pi) * 0.5 + 0.5
        n = fbm(u, v, 40, seed + 2, 3)
        value = 0.88 + grain * 0.08 + n * 0.06
        return (br * value * (1.0 + grain * 0.08), bg * value * 0.98, bb * value * 0.93)
    if pattern == "roof":
        rows = math.sin(v * 16.0 * math.pi) * 0.5 + 0.5
        seams = math.sin(u * 8.0 * math.pi) * 0.5 + 0.5
        n = fbm(u, v, 42, seed + 1, 2)
        value = 0.84 + rows * 0.12 + seams * 0.04 + n * 0.06
        return (br * value * 0.95, bg * value, bb * value * 1.08)
    if pattern == "lacquer":
        n = fbm(u, v, 11, seed, 4)
        value = 0.94 + n * 0.1
        return (br * value, bg * value * 0.97, bb * value * 0.93)
    if pattern == "metal":
        streak = math.sin(v * 90.0 * math.pi + fbm(u, v, 7, seed, 2) * 3.0) * 0.5 + 0.5
        n = fbm(u, v, 13, seed, 3)
        value = 0.84 + streak * 0.18 + n * 0.08
        return (br * value, bg * value * 0.99, bb * value * 0.94)
    if pattern == "paper":
        fiber = abs(math.sin((u * 13.0 + v * 19.0 + fbm(u, v, 6, seed, 3) * 4.0) * math.pi))
        n = fbm(u, v, 20, seed + 2, 3)
        value = 0.95 + fiber * 0.04 + n * 0.04
        return (min(255, br * value), min(255, bg * value * 0.99), min(255, bb * value * 0.95))
    if pattern == "cloth":
        warp = math.sin(u * 46.0 * math.pi) * 0.5 + 0.5
        weft = math.sin(v * 46.0 * math.pi) * 0.5 + 0.5
        n = fbm(u, v, 26, seed, 2)
        value = 0.9 + warp * 0.04 + weft * 0.04 + n * 0.04
        return (br * value, bg * value * 0.98, bb * value * 0.95)
    if pattern == "bark":
        ridges = math.sin(u * 34.0 * math.pi + fbm(u, v, 5, seed, 3) * 5.0) * 0.5 + 0.5
        n = fbm(u, v, 15, seed + 3, 3)
        value = 0.8 + ridges * 0.16 + n * 0.08
        return (br * value, bg * value * 0.97, bb * value * 0.95)
    if pattern == "blossom":
        n = fbm(u, v, 8, seed, 4)
        value = 0.86 + n * 0.2
        return (br * value, bg * value * 0.94, bb * value * 0.98)
    return (br, bg, bb)


def clamp_byte(value: float) -> int:
    return max(0, min(255, int(value)))


def write_maps(name: str, spec: dict, out_dir: Path):
    seed = sum(ord(c) for c in name)
    base = rgb(spec["color"])
    pattern = spec["pattern"]
    size = spec["size"]

    # Height is computed once on a wrapped grid; normals come from neighbour
    # differences, which keeps 512 px generation fast in pure Python.
    height = [0.0] * ((size + 1) * (size + 1))
    for y in range(size + 1):
        v = y / size
        row = y * (size + 1)
        for x in range(size + 1):
            height[row + x] = height_for(pattern, x / size, v, seed)

    base_pixels = []
    normal_pixels = []
    rough_pixels = []
    # Neighbour differences are tiny per texel; a constant slope gain keeps the
    # baked normals readable without turning every material into crushed foil.
    normal_strength = spec["normal"] * 6.0
    for y in range(size):
        v = (y + 0.5) / size
        row = y * (size + 1)
        for x in range(size):
            u = (x + 0.5) / size
            base_pixels.append(
                tuple(clamp_byte(c) for c in shade(pattern, u, v, base, seed))
            )
            hl = height[row + x]
            hr = height[row + x + 1]
            hd = height[row + x]
            hu = height[row + (size + 1) + x]
            nx, ny, nz = (hl - hr) * normal_strength, (hd - hu) * normal_strength, 1.0
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            normal_pixels.append(
                (
                    clamp_byte((nx / length * 0.5 + 0.5) * 255),
                    clamp_byte((ny / length * 0.5 + 0.5) * 255),
                    clamp_byte((nz / length * 0.5 + 0.5) * 255),
                )
            )
            detail = fbm(u, v, 11, seed + 7, 3)
            rough = spec["roughness"] * (0.9 + detail * 0.2)
            if pattern in {"paving", "stone"}:
                rough += (1.0 - mortar_height(u, v, 4, 8)) * 0.1 if pattern == "paving" else 0.0
            value = clamp_byte(rough * 255)
            rough_pixels.append((value, value, value))

    stem = f"T_{name}"
    base_path = out_dir / f"{stem}_BaseColor.jpg"
    normal_path = out_dir / f"{stem}_Normal.jpg"
    rough_path = out_dir / f"{stem}_Roughness.jpg"

    base_image = Image.new("RGB", (size, size))
    base_image.putdata(base_pixels)
    base_image.save(base_path, quality=90, subsampling=0)

    normal_image = Image.new("RGB", (size, size))
    normal_image.putdata(normal_pixels)
    normal_image.save(normal_path, quality=92, subsampling=0)

    rough_image = Image.new("RGB", (size, size))
    rough_image.putdata(rough_pixels)
    rough_image.save(rough_path, quality=86, subsampling=0)
    return base_path, normal_path, rough_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {"tile_meters": 2.4, "materials": {}}
    if args.only and (args.out / "manifest.json").exists():
        manifest = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
    for name, spec in MATERIALS.items():
        if args.only and name not in args.only:
            continue
        base_path, normal_path, rough_path = write_maps(name, spec, args.out)
        manifest["materials"][name] = {
            "base_color": str(base_path.relative_to(ROOT)).replace("\\", "/"),
            "normal": str(normal_path.relative_to(ROOT)).replace("\\", "/"),
            "roughness": str(rough_path.relative_to(ROOT)).replace("\\", "/"),
            "size": spec["size"],
            "pattern": spec["pattern"],
        }
        print("TEXTURE", name, spec["size"], spec["pattern"])
    for alias, source in ALIASES.items():
        if source in manifest["materials"]:
            manifest["materials"][alias] = dict(manifest["materials"][source])
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("LR_TEXTURES_OK", len(manifest["materials"]), args.out)


if __name__ == "__main__":
    main()
