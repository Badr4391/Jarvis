#!/usr/bin/env python3
"""Erzeugt die App-Icons ohne Bildbibliothek - reines zlib/struct PNG.

    python3 scripts/make_icons.py

Schreibt icon-192.png, icon-512.png und icon-maskable-512.png nach
src/jarvis/api/web/. Nur noetig, wenn du Farbe oder Form aenderst.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "api" / "web"

BG = (26, 26, 25)          # dark chart surface #1a1a19
FG = (57, 135, 229)        # series blue #3987e5
DOT = (12, 163, 12)        # status good #0ca30c


def _rounded(x: int, y: int, size: int, radius: float) -> bool:
    """Innerhalb eines abgerundeten Quadrats?"""
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def _pixels(size: int, *, maskable: bool) -> list[list[tuple[int, int, int, int]]]:
    """Ein 'J' aus Stamm, echtem Bogen und Serife - lesbar auch bei 48 px."""
    pad = size * 0.16 if maskable else 0.0         # Sicherheitszone fuer Android
    inner = size - 2 * pad
    radius = size * 0.22

    stroke = inner * 0.135                          # Strichstaerke
    top_y = pad + inner * 0.20                      # Oberkante der Serife
    hook_r = inner * 0.205                          # Radius des Bogens
    hook_cy = pad + inner * 0.60                    # Mitte des Bogens
    stem_cx = pad + inner * 0.60                    # Mittelachse des Stamms
    bar_left = pad + inner * 0.33
    bar_right = stem_cx + stroke / 2
    dot_cx, dot_cy, dot_r = pad + inner * 0.82, pad + inner * 0.18, inner * 0.09

    half = stroke / 2
    hook_ring_cx = stem_cx - hook_r

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            if not maskable and not _rounded(x, y, size, radius):
                row.append((0, 0, 0, 0))
                continue

            colour = BG
            on_stem = abs(x - stem_cx) <= half and top_y <= y <= hook_cy
            on_bar = top_y <= y <= top_y + stroke and bar_left <= x <= bar_right
            on_hook = False
            if y > hook_cy:                          # untere Haelfte des Rings
                distance = ((x - hook_ring_cx) ** 2 + (y - hook_cy) ** 2) ** 0.5
                on_hook = abs(distance - hook_r) <= half

            if on_stem or on_bar or on_hook:
                colour = FG
            if (x - dot_cx) ** 2 + (y - dot_cy) ** 2 <= dot_r ** 2:
                colour = DOT

            row.append((*colour, 255))
        rows.append(row)
    return rows


def write_png(path: Path, rows: list[list[tuple[int, int, int, int]]]) -> None:
    height, width = len(rows), len(rows[0])
    raw = b"".join(
        b"\x00" + b"".join(struct.pack("BBBB", *px) for px in row) for row in rows
    )

    def chunk(tag: bytes, payload: bytes) -> bytes:
        data = tag + payload
        return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    print(f"{path.name}: {width}x{height}, {len(png) // 1024} KB")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_png(OUT_DIR / "icon-192.png", _pixels(192, maskable=False))
    write_png(OUT_DIR / "icon-512.png", _pixels(512, maskable=False))
    write_png(OUT_DIR / "icon-maskable-512.png", _pixels(512, maskable=True))


if __name__ == "__main__":
    main()
