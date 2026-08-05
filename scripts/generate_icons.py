#!/usr/bin/env python3
"""
CloneUp icons — derive sizes/ICO from design masters (no invented glyph by default).

Masters (required unless --invent-placeholder):
  assets/icons/masters/icon-512.png
  assets/icons/masters/icon-512-dark.png
  assets/icons/masters/mark-glyph.png

Outputs:
  assets/icons/icon-{16,24,32,48,64,128,256,512}.png
  assets/icons/icon-512-dark.png
  assets/icons/mark-glyph.png
  assets/icons/CloneUp.ico
  + mirror → desin/icon/assets/

  .\\.venv\\Scripts\\python.exe scripts\\generate_icons.py
  .\\.venv\\Scripts\\python.exe scripts\\generate_icons.py --invent-placeholder
"""

from __future__ import annotations

import argparse
import struct
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icons"
MASTERS = OUT / "masters"
DESIN_ASSETS = ROOT / "desin" / "icon" / "assets"

# desin/icon palette (placeholder invent only)
TEAL = (0x1F, 0x6F, 0x5C, 255)
TEAL_BRIGHT = (0x46, 0xA6, 0x85, 255)
CREAM = (0xF6, 0xF2, 0xE8, 255)
DARK_TILE = (0x2B, 0x28, 0x21, 255)

SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
MASTER_NAMES = ("icon-512.png", "icon-512-dark.png", "mark-glyph.png")


def save_png(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")
    print(f"  wrote {path.relative_to(ROOT)} ({img.size[0]}x{img.size[1]})")


def build_ico(png_by_size: dict[int, Image.Image], path: Path) -> None:
    """Multi-size ICO with exact per-size PNG frames."""
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


def resize_cover(src: Image.Image, size: int) -> Image.Image:
    """High-quality square resize (masters should already be square)."""
    im = src.convert("RGBA")
    if im.size == (size, size):
        return im
    return im.resize((size, size), Image.Resampling.LANCZOS)


def load_masters() -> dict[str, Image.Image]:
    missing = [n for n in MASTER_NAMES if not (MASTERS / n).is_file()]
    if missing:
        raise FileNotFoundError(
            "원본 마스터가 없습니다:\n  "
            + "\n  ".join(str(MASTERS / n) for n in missing)
            + "\n\n디자인 툴에서 export 후 masters/ 에 넣고 다시 실행하세요.\n"
            "임시 플레이스홀더만 필요하면: --invent-placeholder\n"
            "자세한 검증: docs/ICON_CROSS_VERIFY.md"
        )
    out: dict[str, Image.Image] = {}
    for n in MASTER_NAMES:
        out[n] = Image.open(MASTERS / n).convert("RGBA")
        print(f"  master {n}: {out[n].size}")
    return out


def derive_from_masters(masters: dict[str, Image.Image]) -> None:
    light = masters["icon-512.png"]
    dark = masters["icon-512-dark.png"]
    glyph = masters["mark-glyph.png"]

    light_tiles: dict[int, Image.Image] = {}
    for s in SIZES:
        light_tiles[s] = resize_cover(light, s)
        if s != 512:
            save_png(light_tiles[s], OUT / f"icon-{s}.png")
    save_png(resize_cover(light, 512), OUT / "icon-512.png")
    save_png(resize_cover(dark, 512), OUT / "icon-512-dark.png")
    save_png(resize_cover(glyph, 512), OUT / "mark-glyph.png")

    # 16–32: design allows simplified masters if provided as optional files
    for s in (16, 24, 32):
        simple = MASTERS / f"icon-{s}.png"
        if simple.is_file():
            light_tiles[s] = Image.open(simple).convert("RGBA")
            save_png(light_tiles[s], OUT / f"icon-{s}.png")
            print(f"  using simplified master icon-{s}.png")

    build_ico(light_tiles, OUT / "CloneUp.ico")
    _mirror()


def _mirror() -> None:
    DESIN_ASSETS.mkdir(parents=True, exist_ok=True)
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
            (DESIN_ASSETS / name).write_bytes(src.read_bytes())
            print(f"  mirrored desin/icon/assets/{name}")


# ----- legacy invent (explicit only) -----
def _rr(draw: ImageDraw.ImageDraw, box, radius: float, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _chevron(draw, cx, top, ch, color) -> None:
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


def _draw_glyph_on(base, *, cx, cy, scale, color, simple) -> None:
    s = scale
    pw, ph = s * 0.40, s * 0.48
    r = max(1.0, s * 0.09)
    draw = ImageDraw.Draw(base)
    if simple:
        x0, y0 = cx - pw * 0.42, cy - ph * 0.28
        _rr(draw, (x0, y0, x0 + pw * 0.92, y0 + ph * 0.92), r, color)
        _chevron(draw, cx, cy - s * 0.48, s * 0.15, color)
        return
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ox, oy = s * 0.11, s * 0.09
    bx0 = cx - pw * 0.52 + ox
    by0 = cy - ph * 0.32 + oy
    back = (color[0], color[1], color[2], int(color[3] * 0.55))
    _rr(ld, (bx0, by0, bx0 + pw, by0 + ph), r, back)
    base.alpha_composite(layer)
    fx0 = cx - pw * 0.52
    fy0 = cy - ph * 0.32
    _rr(draw, (fx0, fy0, fx0 + pw, fy0 + ph), r, color)
    _chevron(draw, cx, cy - s * 0.50, s * 0.13, color)


def render_tile(size, *, tile_rgba, glyph_rgba, corner_ratio=0.22) -> Image.Image:
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
    if size >= 48 and not simple:
        s = mark
        pw, ph = s * 0.40, s * 0.48
        fx0 = size / 2 - pw * 0.52
        fy0 = size / 2 + size * 0.03 - ph * 0.32
        d2 = ImageDraw.Draw(img)
        for t in (0.36, 0.52, 0.68):
            y = fy0 + ph * t
            d2.line(
                [(fx0 + pw * 0.20, y), (fx0 + pw * 0.80, y)],
                fill=tile_rgba,
                width=max(1, size // 64),
            )
    return img


def invent_placeholder() -> None:
    print("WARNING: inventing placeholder glyph (NOT design-original).")
    print("  See docs/ICON_CROSS_VERIFY.md — replace with masters ASAP.")
    light_tiles: dict[int, Image.Image] = {}
    for s in SIZES:
        light_tiles[s] = render_tile(s, tile_rgba=TEAL, glyph_rgba=CREAM)
    dark_512 = render_tile(512, tile_rgba=DARK_TILE, glyph_rgba=TEAL_BRIGHT)
    glyph = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    _draw_glyph_on(
        glyph, cx=256, cy=256 + 10, scale=512 * 0.62, color=TEAL, simple=False
    )

    save_png(light_tiles[512], OUT / "icon-512.png")
    save_png(dark_512, OUT / "icon-512-dark.png")
    save_png(glyph, OUT / "mark-glyph.png")
    for s in (16, 24, 32, 48, 64, 128, 256):
        save_png(light_tiles[s], OUT / f"icon-{s}.png")
    build_ico(light_tiles, OUT / "CloneUp.ico")
    _mirror()


def main() -> int:
    ap = argparse.ArgumentParser(description="CloneUp icon pipeline")
    ap.add_argument(
        "--invent-placeholder",
        action="store_true",
        help="Draw temporary glyph (not original design). Default: masters only.",
    )
    args = ap.parse_args()

    print(f"CloneUp icons → {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)

    if args.invent_placeholder:
        invent_placeholder()
        print("OK — placeholder only (not original)")
        return 0

    try:
        masters = load_masters()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    derive_from_masters(masters)
    print("OK — derived from design masters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
