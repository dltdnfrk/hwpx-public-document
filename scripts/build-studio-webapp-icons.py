#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Resources" / "Studio" / "icons"
MASTER = 1024
ACCENT = (0x00, 0x68, 0x79, 255)
ACCENT_STRONG = (0x00, 0x53, 0x61, 255)
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
BRAND_MARK_RADII_28 = (7, 7, 7, 2)
RADII: tuple[int, int, int, int] = (
    round(MASTER * BRAND_MARK_RADII_28[0] / 28),
    round(MASTER * BRAND_MARK_RADII_28[1] / 28),
    round(MASTER * BRAND_MARK_RADII_28[2] / 28),
    round(MASTER * BRAND_MARK_RADII_28[3] / 28),
)


def lerp(left: tuple[int, ...], right: tuple[int, ...], t: float) -> tuple[int, ...]:
    return tuple(int(a + (b - a) * t) for a, b in zip(left, right))


def rounded_mask(size: int, radii: tuple[int, int, int, int]) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    tl, tr, br, bl = radii
    draw.rectangle((tl, 0, size - tr, size), fill=255)
    draw.rectangle((0, tl, size, size - bl), fill=255)
    draw.pieslice((0, 0, tl * 2, tl * 2), 180, 270, fill=255)
    draw.pieslice((size - tr * 2, 0, size, tr * 2), 270, 360, fill=255)
    draw.pieslice((size - br * 2, size - br * 2, size, size), 0, 90, fill=255)
    draw.pieslice((0, size - bl * 2, bl * 2, size), 90, 180, fill=255)
    return mask


def draw_name(image: Image.Image, lines: tuple[str, str], size: int) -> None:
    font = ImageFont.truetype(FONT, size=size, index=6)
    draw = ImageDraw.Draw(image)
    boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    heights = [box[3] - box[1] for box in boxes]
    gap = int(size * 0.12)
    block = sum(heights) + gap
    y = (MASTER - block) / 2 - boxes[0][1]
    for line, box, height in zip(lines, boxes, heights):
        x = (MASTER - (box[2] - box[0])) / 2 - box[0]
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += height + gap


def paint_master() -> Image.Image:
    image = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(MASTER):
        for x in range(MASTER):
            t = (x * 0.72 + y * 1.0) / (MASTER * 1.72)
            pixels[x, y] = lerp(ACCENT, ACCENT_STRONG, min(max(t, 0.0), 1.0))
    image.putalpha(rounded_mask(MASTER, RADII))
    highlight = Image.new("L", (MASTER, MASTER), 0)
    ImageDraw.Draw(highlight).rectangle((0, 0, MASTER, max(8, MASTER // 48)), fill=61)
    highlight = highlight.filter(ImageFilter.GaussianBlur(radius=MASTER / 90))
    sheen = Image.new("RGBA", (MASTER, MASTER), (255, 255, 255, 0))
    sheen.putalpha(ImageChops.multiply(highlight, rounded_mask(MASTER, RADII)))
    image = Image.alpha_composite(image, sheen)

    draw_name(image, ("문서", "작성기"), int(MASTER * 0.24))
    return image


def svg_mark() -> str:
    tl, tr, br, bl = BRAND_MARK_RADII_28
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" role="img" aria-label="문서작성기">
  <defs>
    <linearGradient id="mark" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#006879"/>
      <stop offset="1" stop-color="#005361"/>
    </linearGradient>
  </defs>
  <path fill="url(#mark)" d="M{tl},0 H{28 - tr} A{tr},{tr} 0 0 1 28,{tr} V{28 - br} A{br},{br} 0 0 1 {28 - br},28 H{bl} A{bl},{bl} 0 0 1 0,{28 - bl} V{tl} A{tl},{tl} 0 0 1 {tl},0 Z"/>
  <text x="14" y="12.2" text-anchor="middle" fill="#fff" font-family="Apple SD Gothic Neo, sans-serif" font-weight="700" font-size="8">문서</text>
  <text x="14" y="21.4" text-anchor="middle" fill="#fff" font-family="Apple SD Gothic Neo, sans-serif" font-weight="700" font-size="8">작성기</text>
</svg>
"""


def write_png(image: Image.Image, name: str, size: int) -> None:
    resized = image.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(OUT / name, format="PNG", optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    master = paint_master()
    (OUT / "icon.svg").write_text(svg_mark(), encoding="utf-8")
    write_png(master, "icon-1024.png", 1024)
    write_png(master, "icon-512.png", 512)
    write_png(master, "icon-192.png", 192)
    write_png(master, "icon-180.png", 180)
    write_png(master, "apple-touch-icon.png", 180)
    write_png(master, "icon-32.png", 32)
    write_png(master, "icon-16.png", 16)
    master.resize((256, 256), Image.Resampling.LANCZOS).save(
        OUT / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
    manifest = {
        "name": "문서작성기",
        "short_name": "문서작성기",
        "description": "문서작성기",
        "lang": "ko",
        "start_url": "/Studio/index.html",
        "display": "standalone",
        "background_color": "#DFE4E3",
        "theme_color": "#006879",
        "icons": [
            {"src": "icon.svg", "type": "image/svg+xml", "sizes": "any", "purpose": "any"},
            {"src": "icon-192.png", "type": "image/png", "sizes": "192x192", "purpose": "any"},
            {"src": "icon-512.png", "type": "image/png", "sizes": "512x512", "purpose": "any maskable"},
        ],
    }
    (OUT / "site.webmanifest").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
