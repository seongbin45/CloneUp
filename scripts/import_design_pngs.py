#!/usr/bin/env python3
"""
Import CloneUp design PNG exports → assets/icons (+ masters).

Sources in desin/icon/png/:
  - CloneUp Logo-selection (10).png  — size strip (light tiles)
  - CloneUp Logo-selection.png       — brand board (dark tile + glyph)
"""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PNG_DIR = ROOT / "desin" / "icon" / "png"
OUT = ROOT / "assets" / "icons"
MASTERS = OUT / "masters"
STANDARDS = (16, 24, 32, 48, 64, 128, 256, 512)


def is_teal_tile(r: int, g: int, b: int, a: int) -> bool:
    """Solid teal app-tile background (#1f6f5c family)."""
    if a < 200:
        return False
    return 10 < r < 90 and 80 < g < 160 and 60 < b < 130 and g > r + 25 and g >= b


def is_cream(r: int, g: int, b: int, a: int) -> bool:
    if a < 180:
        return False
    return r > 200 and g > 195 and b > 175 and abs(r - g) < 35


def is_bright_teal(r: int, g: int, b: int, a: int) -> bool:
    """Dark-mode glyph teal (#46a685)."""
    if a < 180:
        return False
    return 40 < r < 120 and 130 < g < 210 and 90 < b < 170 and g > r + 30


def is_dark_tile(r: int, g: int, b: int, a: int) -> bool:
    if a < 200:
        return False
    return 20 < r < 70 and 20 < g < 60 and 15 < b < 55 and abs(r - g) < 25


def content_cols(im: Image.Image, pred) -> list[int]:
    w, h = im.size
    px = im.load()
    col = [0] * w
    for x in range(w):
        n = 0
        for y in range(h):
            r, g, b, a = px[x, y]
            if pred(r, g, b, a):
                n += 1
        col[x] = n
    return col


def runs_from_col(col: list[int], min_n: int = 4) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    in_run = False
    start = 0
    for x, n in enumerate(col):
        if n >= min_n and not in_run:
            in_run = True
            start = x
        elif n < min_n and in_run:
            in_run = False
            runs.append((start, x))
    if in_run:
        runs.append((start, len(col)))
    # drop noise runs
    return [(a, b) for a, b in runs if b - a >= 8]


def square_pad(im: Image.Image) -> Image.Image:
    cw, ch = im.size
    side = max(cw, ch)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(im, ((side - cw) // 2, (side - ch) // 2), im)
    return sq


def crop_tile_from_band(im: Image.Image, x0: int, x1: int) -> Image.Image | None:
    """
    Crop one light teal rounded-square tile from a horizontal band.
    Ignores '256px' labels (low-sat gray text below the tile).
    """
    w, h = im.size
    px = im.load()
    # teal+cream vertical extent in band
    miny, maxy = h, -1
    for y in range(h):
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if is_teal_tile(r, g, b, a) or is_cream(r, g, b, a):
                miny = min(miny, y)
                maxy = max(maxy, y)
    if maxy < 0:
        return None
    # refine x to teal+cream only
    minx, maxx = x1, x0
    for y in range(miny, maxy + 1):
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if is_teal_tile(r, g, b, a) or is_cream(r, g, b, a):
                minx = min(minx, x)
                maxx = max(maxx, x)
    if maxx < minx:
        return None
    # force square from top of tile (drop label below if any crept in)
    side = max(maxx - minx + 1, maxy - miny + 1)
    # prefer width of teal body as side
    teal_w = maxx - minx + 1
    side = teal_w
    # top-align square so bottom label is excluded
    y1 = miny + side
    if y1 > h:
        y1 = h
        miny = max(0, y1 - side)
    crop = im.crop((minx, miny, minx + side, miny + side))
    return crop


def extract_strip(path: Path) -> dict[int, Image.Image]:
    im = Image.open(path).convert("RGBA")
    col = content_cols(im, lambda r, g, b, a: is_teal_tile(r, g, b, a) or is_cream(r, g, b, a))
    runs = runs_from_col(col, min_n=6)
    print(f"strip teal runs: {[(a, b, b - a) for a, b in runs]}")

    by_std: dict[int, Image.Image] = {}
    for a, b in runs:
        tile = crop_tile_from_band(im, a, b)
        if tile is None:
            continue
        side = tile.size[0]
        best = min(STANDARDS, key=lambda s: abs(s - side))
        # allow larger tolerance for anti-alias
        if abs(best - side) > max(10, int(best * 0.25)):
            print(f"  skip side={side}")
            continue
        if tile.size != (best, best):
            tile = tile.resize((best, best), Image.Resampling.LANCZOS)
        # keep larger source when conflict
        if best not in by_std or side > by_std[best].size[0]:
            by_std[best] = tile
            print(f"  strip → {best}px (raw ~{side})")
    return by_std


def dark_from_light(light: Image.Image) -> Image.Image:
    """
    Design dark tile = same mark as light with recolored surfaces:
      tile #1f6f5c → #2b2821, cream glyph → #46a685
    (more reliable than cropping the brand board card)
    """
    im = light.convert("RGBA").copy()
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 8:
                continue
            if is_cream(r, g, b, a) or (r > 180 and g > 175 and b > 160 and a > 100):
                # cream → bright teal (preserve alpha for AA)
                px[x, y] = (0x46, 0xA6, 0x85, a)
            elif is_teal_tile(r, g, b, a) or (g > r + 15 and 60 < g < 170 and r < 100):
                px[x, y] = (0x2B, 0x28, 0x21, a)
    print("  dark tile recolored from light master")
    return im


def glyph_from_light(light: Image.Image) -> Image.Image:
    """Monochrome mark: only cream glyph → #1f6f5c; drop tile entirely (no outline)."""
    im = light.convert("RGBA").copy()
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            # strict cream (arrow + step body) — exclude teal tile AA fringe
            if a > 40 and r > 200 and g > 195 and b > 170 and min(r, g, b) > 160:
                px[x, y] = (0x1F, 0x6F, 0x5C, a)
            else:
                px[x, y] = (0, 0, 0, 0)
    print("  glyph derived from light master")
    return im


def build_ico(by_size: dict[int, Image.Image], path: Path) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images: list[Image.Image] = []
    master = by_size.get(512) or by_size[max(by_size)]
    for s in sizes:
        if s in by_size:
            images.append(by_size[s].convert("RGBA"))
        else:
            images.append(master.resize((s, s), Image.Resampling.LANCZOS))
    blobs: list[bytes] = []
    for im in images:
        buf = BytesIO()
        im.save(buf, format="PNG")
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
    print(f"  ico {path.stat().st_size} bytes")


def mirror() -> None:
    dest = ROOT / "desin" / "icon" / "assets"
    dest.mkdir(parents=True, exist_ok=True)
    for name in (
        "icon-512.png",
        "icon-512-dark.png",
        "mark-glyph.png",
        *(f"icon-{s}.png" for s in (16, 24, 32, 48, 64, 128, 256)),
        "CloneUp.ico",
    ):
        src = OUT / name
        if src.is_file():
            (dest / name).write_bytes(src.read_bytes())


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    MASTERS.mkdir(parents=True, exist_ok=True)

    strip_path = PNG_DIR / "CloneUp Logo-selection (10).png"
    board_path = PNG_DIR / "CloneUp Logo-selection.png"
    if not strip_path.is_file() or not board_path.is_file():
        raise SystemExit("need strip (10) and full board selection.png in desin/icon/png/")

    print("== light tiles from size strip ==")
    by_std = extract_strip(strip_path)
    if 512 not in by_std:
        # upscale best available
        best = max(by_std, default=None)
        if best is None:
            raise SystemExit("no strip icons")
        by_std[512] = by_std[best].resize((512, 512), Image.Resampling.LANCZOS)
        print(f"  512 upscaled from {best}")

    light = by_std[512]
    light.save(MASTERS / "icon-512.png")
    light.save(OUT / "icon-512.png")

    for s in STANDARDS:
        if s == 512:
            continue
        img = by_std.get(s) or light.resize((s, s), Image.Resampling.LANCZOS)
        if s not in by_std:
            print(f"  resize fallback → {s}")
        img.save(OUT / f"icon-{s}.png")
        by_std[s] = img
        if s in (16, 24, 32):
            img.save(MASTERS / f"icon-{s}.png")

    print("== dark + glyph (recolor from light master) ==")
    dark = dark_from_light(light)
    glyph = glyph_from_light(light)
    dark.save(MASTERS / "icon-512-dark.png")
    dark.save(OUT / "icon-512-dark.png")
    glyph.save(MASTERS / "mark-glyph.png")
    glyph.save(OUT / "mark-glyph.png")

    build_ico(by_std, OUT / "CloneUp.ico")
    mirror()
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
