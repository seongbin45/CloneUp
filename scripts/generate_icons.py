#!/usr/bin/env python3
"""
Generate CloneUp app icons from desin/icon identity tokens.

Outputs (I1 + I2):
  assets/icons/icon-512.png
  assets/icons/icon-512-dark.png
  assets/icons/mark-glyph.png
  assets/icons/icon-{16,24,32,48,64,128,256}.png
  assets/icons/CloneUp.ico

Also mirrors into desin/icon/assets/ for the HTML mock.

  .\\.venv\\Scripts\\python.exe scripts\\generate_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icons"
DESIN_ASSETS = ROOT / "desin" / "icon" / "assets"

# desin/icon palette strip
TEAL = (0x1F, 0x6F, 0x5C, 255)
TEAL_BRIGHT = (0x46, 0xA6, 0x85, 255)
CREAM = (0xF6, 0xF2, 0xE8, 255)
DARK_TILE = (0x2B, 0x28, 0x21, 255)

SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def _rr(draw: ImageDraw.ImageDraw, box, radius: float, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _chevron(
    draw: ImageDraw.ImageDraw,
    cx: float,
    top: float,
    ch: float,
    color: tuple[int, int, int, int],
) -> None:
    draw.polygon(
        [
            (cx, top),
            (cx - ch * 1.15, top + ch * 1.25),
            (cx - ch * 0.38, top + ch * 1.25),
            (cx - ch * 0.38, top + ch * 2.05),
            (cx + ch * 0.38, top + ch * 2.05),
            (cx + ch * 0.38, top + ch * 1.25),
            (cx + ch * 1.15, top + ch * 1.25),
        ],
        fill=color,
    )


def _draw_glyph_on(
    base: Image.Image,
    *,
    cx: float,
    cy: float,
    scale: float,
    color: tuple[int, int, int, int],
    simple: bool,
) -> None:
    """
    CloneUp mark: two offset rounded 'pages' (clone) + up chevron.
    Back page is drawn at lower alpha so layers stay readable.
    """
    s = scale
    pw, ph = s * 0.40, s * 0.48
    r = max(1.0, s * 0.09)
    draw = ImageDraw.Draw(base)

    if simple:
        x0, y0 = cx - pw * 0.42, cy - ph * 0.28
        _rr(draw, (x0, y0, x0 + pw * 0.92, y0 + ph * 0.92), r, color)
        _chevron(draw, cx, cy - s * 0.48, s * 0.15, color)
        return

    # back page layer (offset, 55% opacity)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ox, oy = s * 0.11, s * 0.09
    bx0 = cx - pw * 0.52 + ox
    by0 = cy - ph * 0.32 + oy
    back = (color[0], color[1], color[2], int(color[3] * 0.55))
    _rr(ld, (bx0, by0, bx0 + pw, by0 + ph), r, back)
    base.alpha_composite(layer)

    # front page solid
    fx0 = cx - pw * 0.52
    fy0 = cy - ph * 0.32
    _rr(draw, (fx0, fy0, fx0 + pw, fy0 + ph), r, color)

    # thin "lines" punched with tile-color is done by caller for tiles;
    # for mono glyph, draw slightly transparent slits
    if s >= 40:
        line = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ld2 = ImageDraw.Draw(line)
        # destination-out style: erase with transparent by compositing black then...
        # simpler: draw darker inset lines only when glyph is light-on-teal handled elsewhere
        inset_x = fx0 + pw * 0.18
        for i, t in enumerate((0.32, 0.48, 0.64)):
            y = fy0 + ph * t
            # leave as solid glyph — lines need hole; skip for monochrome clarity
            _ = (inset_x, y, i)
        del ld2, line

    _chevron(draw, cx, cy - s * 0.50, s * 0.13, color)


def render_tile(
    size: int,
    *,
    tile_rgba: tuple[int, int, int, int],
    glyph_rgba: tuple[int, int, int, int],
    corner_ratio: float = 0.22,
) -> Image.Image:
    """Rounded-square app icon (Windows-style)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(0, int(round(size * 0.02)))
    radius = max(1.0, (size - 2 * pad) * corner_ratio)
    _rr(draw, (pad, pad, size - 1 - pad, size - 1 - pad), radius, tile_rgba)

    mark = size * 0.50
    simple = size <= 32
    _draw_glyph_on(
        img,
        cx=size / 2,
        cy=size / 2 + size * 0.03,
        scale=mark,
        color=glyph_rgba,
        simple=simple,
    )

    # content lines on front page (tile color) for ≥48px
    if size >= 48 and not simple:
        s = mark
        pw, ph = s * 0.40, s * 0.48
        fx0 = size / 2 - pw * 0.52
        fy0 = size / 2 + size * 0.03 - ph * 0.32
        d2 = ImageDraw.Draw(img)
        for t in (0.36, 0.52, 0.68):
            y = fy0 + ph * t
            x1 = fx0 + pw * 0.20
            x2 = fx0 + pw * 0.80
            d2.line([(x1, y), (x2, y)], fill=tile_rgba, width=max(1, size // 64))
    return img


def render_glyph_only(size: int = 512) -> Image.Image:
    """Tile-free monochrome symbol on transparent."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mark = size * 0.62
    _draw_glyph_on(
        img,
        cx=size / 2,
        cy=size / 2 + size * 0.02,
        scale=mark,
        color=TEAL,
        simple=False,
    )
    return img


def save_png(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")
    print(f"  wrote {path.relative_to(ROOT)} ({img.size[0]}x{img.size[1]})")


def build_ico(png_by_size: dict[int, Image.Image], path: Path) -> None:
    """
    Multi-size ICO with *exact* per-size bitmaps (16–32 simplified glyphs).

    Pillow's ICO saver rescales one source image; we embed PNG frames manually
    so small sizes keep the simplified mark.
    """
    import struct
    from io import BytesIO

    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [png_by_size[s].convert("RGBA") for s in sizes if s in png_by_size]
    png_blobs: list[bytes] = []
    for im in images:
        buf = BytesIO()
        im.save(buf, format="PNG")
        png_blobs.append(buf.getvalue())

    count = len(images)
    offset = 6 + 16 * count
    header = struct.pack("<HHH", 0, 1, count)
    entries = bytearray()
    for im, blob in zip(images, png_blobs):
        w, h = im.size
        wb = 0 if w >= 256 else w
        hb = 0 if h >= 256 else h
        entries += struct.pack("<BBBBHHII", wb, hb, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + bytes(entries) + b"".join(png_blobs))
    print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes, {count} sizes)")


def main() -> int:
    print(f"CloneUp icons → {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    DESIN_ASSETS.mkdir(parents=True, exist_ok=True)

    light_tiles: dict[int, Image.Image] = {}
    for s in SIZES:
        light_tiles[s] = render_tile(s, tile_rgba=TEAL, glyph_rgba=CREAM)

    dark_512 = render_tile(512, tile_rgba=DARK_TILE, glyph_rgba=TEAL_BRIGHT)
    glyph = render_glyph_only(512)

    # I1 masters
    save_png(light_tiles[512], OUT / "icon-512.png")
    save_png(dark_512, OUT / "icon-512-dark.png")
    save_png(glyph, OUT / "mark-glyph.png")

    # I2 size set (light tile — primary window/taskbar)
    for s in (16, 24, 32, 48, 64, 128, 256):
        save_png(light_tiles[s], OUT / f"icon-{s}.png")

    build_ico(light_tiles, OUT / "CloneUp.ico")

    # Mirror for desin HTML mock (relative assets/)
    for name in (
        "icon-512.png",
        "icon-512-dark.png",
        "mark-glyph.png",
        "icon-16.png",
        "icon-24.png",
        "icon-32.png",
        "icon-48.png",
        "icon-64.png",
        "icon-128.png",
        "icon-256.png",
        "CloneUp.ico",
    ):
        src = OUT / name
        if src.is_file():
            dst = DESIN_ASSETS / name
            dst.write_bytes(src.read_bytes())
            print(f"  mirrored desin/icon/assets/{name}")

    print("OK — I1 masters + I2 sizes/ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
