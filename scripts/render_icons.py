#!/usr/bin/env python3
"""
Render crisp CloneUp icons (vector geometry).

Geometry measured from design size-strip 256px export
(desin/icon/png/CloneUp Logo-selection (10).png):
  - rounded square tile, cream stair + up-arrow
  - 16–32: simplified (arrow + bar only)

Outputs assets/icons/* + masters + desin/icon/assets + CloneUp.ico

  .\\.venv\\Scripts\\python.exe scripts\\render_icons.py
"""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icons"
MASTERS = OUT / "masters"
DESIN = ROOT / "desin" / "icon" / "assets"

# Brand tokens (exact from design strip sample)
TEAL = (0x1F, 0x6F, 0x5C, 255)  # #1f6f5c
CREAM = (0xF6, 0xF2, 0xE8, 255)  # #f6f2e8
DARK_TILE = (0x2B, 0x28, 0x21, 255)
BRIGHT = (0x46, 0xA6, 0x85, 255)

# Proportions in unit square [0,1] from 256px design measure
# Tile corner radius / 256 ≈ 18/256
R_CORNER = 18 / 256

# Arrow triangle: tip y=32, base y=80, base x=82..173, center=127.5
# Stem: y=84..109, x=111..144
ARROW_TIP_Y = 32 / 256
ARROW_BASE_Y = 80 / 256
ARROW_BASE_X0 = 82 / 256
ARROW_BASE_X1 = 173 / 256
STEM_Y0 = 84 / 256
STEM_Y1 = 109 / 256
STEM_X0 = 111 / 256
STEM_X1 = 144 / 256

# Step L: top block y=128..163 x=37..108; bar y=164..219 x=37..218
STEP_TOP_Y0 = 128 / 256
STEP_TOP_Y1 = 163 / 256
STEP_TOP_X0 = 37 / 256
STEP_TOP_X1 = 108 / 256
STEP_BAR_Y0 = 164 / 256
STEP_BAR_Y1 = 219 / 256
STEP_BAR_X0 = 37 / 256
STEP_BAR_X1 = 218 / 256
STEP_R = 10 / 256  # step corner radius


def _rr(draw: ImageDraw.ImageDraw, box, radius: float, fill) -> None:
    draw.rounded_rectangle(box, radius=max(0.5, radius), fill=fill)


def render_full(size: int, *, tile: tuple, glyph: tuple) -> Image.Image:
    """Full mark: tile + arrow + stair (crisp at any size)."""
    s = float(size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # slight inset so OS rounding doesn't clip (1px at 256+)
    inset = max(0, round(s * 0.004))
    _rr(
        draw,
        (inset, inset, size - 1 - inset, size - 1 - inset),
        R_CORNER * s,
        tile,
    )

    # --- arrow (triangle + stem, overlap so no gap) ---
    tip_y = ARROW_TIP_Y * s
    base_y = ARROW_BASE_Y * s
    bx0, bx1 = ARROW_BASE_X0 * s, ARROW_BASE_X1 * s
    cx = (bx0 + bx1) / 2
    tri = [(cx, tip_y), (bx0, base_y), (bx1, base_y)]
    draw.polygon(tri, fill=glyph)
    # stem starts at triangle base (overlap 1px) through design STEM_Y1
    draw.rectangle(
        (STEM_X0 * s, base_y - max(1.0, s * 0.01), STEM_X1 * s, STEM_Y1 * s),
        fill=glyph,
    )

    # --- L-shaped step (two rounded rects merged) ---
    r = STEP_R * s
    # left upper platform
    _rr(
        draw,
        (STEP_TOP_X0 * s, STEP_TOP_Y0 * s, STEP_TOP_X1 * s, STEP_TOP_Y1 * s + r),
        r,
        glyph,
    )
    # bottom bar
    _rr(
        draw,
        (STEP_BAR_X0 * s, STEP_BAR_Y0 * s - r * 0.5, STEP_BAR_X1 * s, STEP_BAR_Y1 * s),
        r,
        glyph,
    )
    # fill join (square overlap to hide double radius seam)
    draw.rectangle(
        (
            STEP_TOP_X0 * s + r * 0.2,
            STEP_TOP_Y1 * s - r,
            STEP_TOP_X1 * s - r * 0.2,
            STEP_BAR_Y0 * s + r,
        ),
        fill=glyph,
    )
    return img


def render_simple(size: int, *, tile: tuple, glyph: tuple) -> Image.Image:
    """16–32 simplified: arrow + single bar (design rule)."""
    s = float(size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    inset = max(0, round(s * 0.02)) if size >= 24 else 0
    _rr(
        draw,
        (inset, inset, size - 1 - inset, size - 1 - inset),
        max(1.0, R_CORNER * s),
        tile,
    )

    # compact arrow
    cx = s / 2
    tip_y = s * 0.18
    base_y = s * 0.42
    half = s * 0.22
    draw.polygon(
        [(cx, tip_y), (cx - half, base_y), (cx + half, base_y)],
        fill=glyph,
    )
    sw = s * 0.14
    draw.rectangle((cx - sw / 2, base_y - 1, cx + sw / 2, s * 0.55), fill=glyph)

    # bar
    by0, by1 = s * 0.62, s * 0.78
    bx0, bx1 = s * 0.18, s * 0.82
    br = max(1.0, s * 0.06)
    _rr(draw, (bx0, by0, bx1, by1), br, glyph)
    return img


def render_glyph_only(size: int = 512) -> Image.Image:
    """Monochrome mark on transparent (no tile)."""
    # render cream-on-transparent by drawing full then stripping tile
    full = render_full(size, tile=(0, 0, 0, 0), glyph=TEAL)
    # tile was transparent; glyph is teal — done
    # but rounded rect with alpha0 tile still draws nothing; good
    # re-render: only glyph parts on transparent
    s = float(size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    tip_y = ARROW_TIP_Y * s
    base_y = ARROW_BASE_Y * s
    bx0, bx1 = ARROW_BASE_X0 * s, ARROW_BASE_X1 * s
    cx = (bx0 + bx1) / 2
    draw.polygon([(cx, tip_y), (bx0, base_y), (bx1, base_y)], fill=TEAL)
    draw.rectangle(
        (STEM_X0 * s, base_y - max(1.0, s * 0.01), STEM_X1 * s, STEM_Y1 * s),
        fill=TEAL,
    )
    r = STEP_R * s
    _rr(
        draw,
        (STEP_TOP_X0 * s, STEP_TOP_Y0 * s, STEP_TOP_X1 * s, STEP_TOP_Y1 * s + r),
        r,
        TEAL,
    )
    _rr(
        draw,
        (STEP_BAR_X0 * s, STEP_BAR_Y0 * s - r * 0.5, STEP_BAR_X1 * s, STEP_BAR_Y1 * s),
        r,
        TEAL,
    )
    draw.rectangle(
        (
            STEP_TOP_X0 * s + r * 0.2,
            STEP_TOP_Y1 * s - r,
            STEP_TOP_X1 * s - r * 0.2,
            STEP_BAR_Y0 * s + r,
        ),
        fill=TEAL,
    )
    return img


def build_ico(by_size: dict[int, Image.Image], path: Path) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [by_size[s].convert("RGBA") for s in sizes]
    blobs: list[bytes] = []
    for im in images:
        buf = BytesIO()
        # PNG compress without palette dither
        im.save(buf, format="PNG", optimize=True)
        blobs.append(buf.getvalue())
    count = len(images)
    offset = 6 + 16 * count
    header = struct.pack("<HHH", 0, 1, count)
    entries = bytearray()
    for im, blob in zip(images, blobs):
        w, h = im.size
        wb = 0 if w >= 256 else w
        hb = 0 if h >= 256 else h
        entries += struct.pack("<BBBBHHII", wb, hb, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    path.write_bytes(header + bytes(entries) + b"".join(blobs))
    print(f"  ico {path.stat().st_size} bytes, {count} sizes")


def mirror() -> None:
    DESIN.mkdir(parents=True, exist_ok=True)
    for name in (
        "icon-512.png",
        "icon-512-dark.png",
        "mark-glyph.png",
        *(f"icon-{s}.png" for s in (16, 24, 32, 48, 64, 128, 256)),
        "CloneUp.ico",
    ):
        src = OUT / name
        if src.is_file():
            (DESIN / name).write_bytes(src.read_bytes())


def render_aa(size: int, *, simple: bool, tile: tuple, glyph: tuple, scale: int = 4) -> Image.Image:
    """Draw at higher res then Lanczos-down for clean edges (no screenshot blur)."""
    big = size * scale
    if simple:
        hi = render_simple(big, tile=tile, glyph=glyph)
    else:
        hi = render_full(big, tile=tile, glyph=glyph)
    if scale == 1:
        return hi
    return hi.resize((size, size), Image.Resampling.LANCZOS)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    MASTERS.mkdir(parents=True, exist_ok=True)

    print("Render crisp CloneUp icons (vector geometry + supersample)")
    by: dict[int, Image.Image] = {}

    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        # 512: 2x AA enough; small sizes: 4x
        ss = 2 if size >= 256 else 4
        img = render_aa(
            size,
            simple=size <= 32,
            tile=TEAL,
            glyph=CREAM,
            scale=ss,
        )
        by[size] = img
        img.save(OUT / f"icon-{size}.png")
        print(f"  icon-{size}.png (ss={ss}x)")

    dark = render_aa(512, simple=False, tile=DARK_TILE, glyph=BRIGHT, scale=2)
    dark.save(OUT / "icon-512-dark.png")
    print("  icon-512-dark.png")

    # glyph: supersample monochrome
    g_hi = render_glyph_only(512 * 2)
    glyph = g_hi.resize((512, 512), Image.Resampling.LANCZOS)
    glyph.save(OUT / "mark-glyph.png")
    print("  mark-glyph.png")

    # masters
    by[512].save(MASTERS / "icon-512.png")
    dark.save(MASTERS / "icon-512-dark.png")
    glyph.save(MASTERS / "mark-glyph.png")
    for s in (16, 24, 32):
        by[s].save(MASTERS / f"icon-{s}.png")

    build_ico(by, OUT / "CloneUp.ico")
    mirror()
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
