"""Post-process the Lantern River raw renders and build a contact sheet.

Run:
    python assets/lantern-river/scripts/postprocess_renders.py

Inputs:  assets/lantern-river/renders/raw/*.png
Outputs: assets/lantern-river/renders/*.png
         assets/lantern-river/renders/contact_sheet.png
"""

import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.dirname(HERE)
RAW_DIR = os.path.join(ASSET_DIR, "renders", "raw")
OUT_DIR = os.path.join(ASSET_DIR, "renders")
os.makedirs(OUT_DIR, exist_ok=True)

SHOTS = [
    ("01_hero.png", "桥拱灯楼 · 主视觉"),
    ("02_bridge_approach.png", "桥头 · 拱桥与灯楼"),
    ("03_tower_detail.png", "灯楼 · 五重檐"),
    ("04_street.png", "临水长街 · 灯市"),
    ("05_boat.png", "画舫 · 水上灯影"),
]

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"


def bright_pass(img, threshold=205, radius=14):
    grey = img.convert("L")
    mask = grey.point(lambda v: 0 if v < threshold else min(255, int((v - threshold) * 2.2)))
    glow = Image.new("RGB", img.size, (0, 0, 0))
    glow.paste(img, (0, 0), mask)
    return glow.filter(ImageFilter.GaussianBlur(radius))


def grade(img):
    # Slight lift in the shadows, warm highlights, cool shadows.
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            lum = (r * 0.2126 + g * 0.7152 + b * 0.0722) / 255.0
            # Contrast + saturation.
            r = int((r - 128) * 1.055 + 128)
            g = int((g - 128) * 1.055 + 128)
            b = int((b - 128) * 1.055 + 128)
            avg = (r + g + b) / 3.0
            sat = 1.10
            r = int(avg + (r - avg) * sat)
            g = int(avg + (g - avg) * sat)
            b = int(avg + (b - avg) * sat)
            # Cool shadows / warm highs.
            if lum < 0.45:
                r = int(r * 0.97 + 1.5)
                g = int(g * 0.99 + 2.0)
                b = int(b * 1.06 + 3.0)
            else:
                r = int(r * 1.035)
                g = int(g * 1.015)
                b = int(b * 0.985)
            px[x, y] = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
    return img


def vignette(img, strength=0.38):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    cx, cy = w / 2.0, h / 2.0
    max_r = (cx * cx + cy * cy) ** 0.5
    for y in range(h):
        for x in range(w):
            dx, dy = x - cx, y - cy
            r = (dx * dx + dy * dy) ** 0.5 / max_r
            v = int(255 * max(0.0, min(1.0, (r - 0.42) / 0.58)) ** 1.7 * strength)
            mask.putpixel((x, y), v)
    black = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(black, img, mask)


def grain(img, amount=5, seed=7):
    rng = random.Random(seed)
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            n = rng.randint(-amount, amount)
            r, g, b = px[x, y]
            px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)),
                        max(0, min(255, b + n)))
    return img


def process(name):
    path = os.path.join(RAW_DIR, name)
    img = Image.open(path).convert("RGB")
    glow = bright_pass(img)
    screen = Image.new("RGB", img.size)
    sp, gp = screen.load(), glow.load()
    ip = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b = ip[x, y]
            gr, gg, gb = gp[x, y]
            sp[x, y] = (255 - (255 - r) * (255 - gr) // 255,
                        255 - (255 - g) * (255 - gg) // 255,
                        255 - (255 - b) * (255 - gb) // 255)
    img = screen
    img = grade(img)
    img = vignette(img)
    img = grain(img)
    out = os.path.join(OUT_DIR, name)
    img.save(out, quality=95)
    return out


def contact_sheet(paths):
    if not paths:
        return None
    thumb_w = 880
    gap = 16
    label_h = 46
    first = Image.open(paths[0][0])
    ratio = first.height / first.width
    thumb_h = int(thumb_w * ratio)
    cols = 2
    rows = (len(paths) + cols - 1) // cols
    W = cols * thumb_w + (cols + 1) * gap
    H = rows * (thumb_h + label_h) + (rows + 1) * gap + 64
    sheet = Image.new("RGB", (W, H), (7, 9, 18))
    draw = ImageDraw.Draw(sheet)
    font_title = ImageFont.truetype(FONT_PATH, 30)
    font_label = ImageFont.truetype(FONT_PATH, 19)
    draw.text((gap + 6, 18), "桃源 · 上元灯会  /  Lantern River Night", font=font_title,
              fill=(240, 226, 196))
    for i, (path, label) in enumerate(paths):
        img = Image.open(path).convert("RGB").resize((thumb_w, thumb_h), Image.LANCZOS)
        col = i % cols
        row = i // cols
        x = gap + col * (thumb_w + gap)
        y = 64 + gap + row * (thumb_h + label_h + gap)
        sheet.paste(img, (x, y))
        draw.text((x + 4, y + thumb_h + 10), label, font=font_label, fill=(206, 196, 176))
    out = os.path.join(OUT_DIR, "contact_sheet.png")
    sheet.save(out, quality=95)
    return out


if __name__ == "__main__":
    made = []
    for name, label in SHOTS:
        raw = os.path.join(RAW_DIR, name)
        if not os.path.exists(raw):
            print("missing", raw)
            continue
        print("post", name)
        made.append((process(name), label))
    sheet = contact_sheet(made)
    print("contact_sheet", sheet)
