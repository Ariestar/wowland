"""Post-process Blender renders with a light bloom, vignette and contact sheet.

Pure Pillow; runs on the system Python:
    python assets/lantern/scripts/postprocess_renders.py
"""

import json
import os
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.dirname(HERE)
RAW = os.path.join(ASSET_DIR, "renders", "raw")
OUT = os.path.join(ASSET_DIR, "renders")
os.makedirs(OUT, exist_ok=True)

FONT = "C:/Windows/Fonts/msyh.ttc"


def bright_pass(img, threshold=150, gain=3.0):
    gray = img.convert("L")
    mask = gray.point(lambda p: 0 if p < threshold else min(255, int((p - threshold) * gain)))
    black = Image.new("RGB", img.size, (0, 0, 0))
    return Image.composite(img, black, mask)


def add_bloom(img, threshold=150, radius_small=14, radius_large=42,
              strength_small=0.50, strength_large=0.35):
    bright = bright_pass(img, threshold=threshold)
    b1 = bright.filter(ImageFilter.GaussianBlur(radius=radius_small))
    b2 = bright.filter(ImageFilter.GaussianBlur(radius=radius_large))
    black = Image.new("RGB", img.size, (0, 0, 0))
    b1 = Image.blend(black, b1, strength_small)
    b2 = Image.blend(black, b2, strength_large)
    bloom = ImageChops.screen(b1, b2)
    return ImageChops.screen(img, bloom)


def add_vignette(img, amount=0.32, softness=0.20):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    margin_x = int(w * 0.02)
    margin_y = int(h * 0.02)
    draw.ellipse((margin_x, margin_y, w - margin_x, h - margin_y), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(w, h) * softness))
    dark = ImageEnhance.Brightness(img).enhance(1.0 - amount)
    return Image.composite(img, dark, mask)


def process(src_name, dst_name, threshold=150, bloom_small=0.5, bloom_large=0.35,
            vignette=0.30):
    src = os.path.join(RAW, src_name)
    if not os.path.exists(src):
        print("SKIP missing", src)
        return None
    img = Image.open(src).convert("RGB")
    img = add_bloom(img, threshold=threshold, radius_small=14, radius_large=42,
                    strength_small=bloom_small, strength_large=bloom_large)
    img = add_vignette(img, amount=vignette, softness=0.22)
    img = ImageEnhance.Contrast(img).enhance(1.03)
    img = ImageEnhance.Color(img).enhance(1.05)
    dst = os.path.join(OUT, dst_name)
    img.save(dst)
    print("WROTE", dst)
    return dst


def asset_stats():
    report_path = os.path.join(ASSET_DIR, "reports", "build_report.json")
    try:
        with open(report_path, encoding="utf-8") as handle:
            report = json.load(handle)
        tris = f"{report['triangles']:,}"
        materials = len(report.get("materials", []))
        return tris, materials
    except (OSError, KeyError, ValueError):
        return "?", "?"


def make_contact_sheet(paths, dst_name):
    if len(paths) != 4:
        return None
    thumbs = []
    for path in paths:
        img = Image.open(path).convert("RGB")
        img.thumbnail((480, 600), Image.LANCZOS)
        thumbs.append(img)
    cell_w = max(t.width for t in thumbs) + 28
    cell_h = max(t.height for t in thumbs) + 54
    sheet = Image.new("RGB", (cell_w * 2, cell_h * 2 + 70), (7, 15, 18))
    draw = ImageDraw.Draw(sheet)
    try:
        title_font = ImageFont.truetype(FONT, 26)
        label_font = ImageFont.truetype(FONT, 20)
    except OSError:
        title_font = ImageFont.load_default()
        label_font = ImageFont.load_default()
    tris, materials = asset_stats()
    title = f"SM_PalaceLantern_6S · 六角宫灯 · {tris} tris · {materials} materials"
    draw.text((24, 16), title, fill=(232, 205, 150), font=title_font)
    labels = ["正面 Front", "右侧 Right", "背面 Back", "三分之四 Three-quarter"]
    for i, thumb in enumerate(thumbs):
        col = i % 2
        row = i // 2
        x = col * cell_w + (cell_w - thumb.width) // 2
        y = 70 + row * cell_h
        sheet.paste(thumb, (x, y))
        draw.text((col * cell_w + 24, y + thumb.height + 8), labels[i],
                  fill=(200, 200, 195), font=label_font)
    dst = os.path.join(OUT, dst_name)
    sheet.save(dst)
    print("WROTE", dst)
    return dst


if __name__ == "__main__":
    hero = process("hero.png", "01_hero.png", threshold=155,
                   bloom_small=0.55, bloom_large=0.40, vignette=0.32)
    three = process("three_quarter.png", "02_three_quarter.png", threshold=155,
                    bloom_small=0.50, bloom_large=0.35, vignette=0.30)
    front = process("front.png", "03_front.png", threshold=160,
                    bloom_small=0.35, bloom_large=0.22, vignette=0.24)
    right = process("right.png", "04_right.png", threshold=160,
                    bloom_small=0.35, bloom_large=0.22, vignette=0.24)
    back = process("back.png", "05_back.png", threshold=160,
                   bloom_small=0.35, bloom_large=0.22, vignette=0.24)
    detail = process("detail_roof.png", "06_detail_roof.png", threshold=165,
                     bloom_small=0.35, bloom_large=0.25, vignette=0.28)
    make_contact_sheet([front, right, back, three], "07_turnaround.png")
