#!/usr/bin/env python
"""
Dune 1992 MAP.HSQ Decoder

Decodes the world map terrain data from MAP.HSQ.

MAP.HSQ: 50,681 bytes decompressed (RES_MAP_SIZE = 0x0C5F9).
Contains terrain/region data for the game's flat map and globe views.

The map data is accessed via TABLAT.BIN latitude lookup table for the
globe projection, and linearly for the flat map. Each byte encodes
terrain information used for rendering and gameplay (spice fields,
sietches, rocky terrain, sand, etc.).

Related ASM functions:
  - _sub_1B58B_map_func: map access using TABLAT latitude offsets
  - _sub_1B427_map_func: map data conversion (2-bit extraction)
  - sub_1B473: map region overlay (2-bit bitfield insert)

Related resources:
  - TABLAT.BIN: 99 × 8-byte latitude lookup table
  - GLOBDATA.HSQ: globe rendering parameters
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress
from png import encode_png

RES_MAP_SIZE = 0x0C5F9  # 50681 bytes

# Auto-detected row widths tried for layout (same set as --render).
MAP_RENDER_WIDTHS = [200, 304, 320, 400, 500]
MAP_DEFAULT_WIDTH = 320


def analyze_map(data):
    """Analyze MAP data structure and contents."""
    size = len(data)
    print(f"MAP data: {size} bytes (expected {RES_MAP_SIZE})")

    # Value distribution
    hist = [0] * 256
    for b in data:
        hist[b] += 1

    print(f"\nByte value distribution:")
    print(f"  {'Value':>5}  {'Count':>6}  {'Pct':>5}  Bar")
    print(f"  {'-'*5}  {'-'*6}  {'-'*5}  {'-'*40}")
    for v in range(256):
        if hist[v] > 0:
            pct = hist[v] * 100.0 / size
            bar = '#' * min(40, int(pct))
            print(f"  0x{v:02X}  {hist[v]:6d}  {pct:4.1f}%  {bar}")

    # Unique values
    unique = sorted(set(data))
    print(f"\nUnique values ({len(unique)}): {', '.join(f'0x{v:02X}' for v in unique)}")

    # Run analysis
    runs = []
    i = 0
    while i < size:
        run_val = data[i]
        run_len = 1
        while i + run_len < size and data[i + run_len] == run_val:
            run_len += 1
        if run_len >= 8:
            runs.append((i, run_len, run_val))
        i += run_len

    print(f"\nLong runs (≥8 identical bytes): {len(runs)}")
    if runs:
        print(f"  Top 20 longest:")
        for offset, length, val in sorted(runs, key=lambda r: -r[1])[:20]:
            print(f"    offset=0x{offset:04X}  len={length:5d}  val=0x{val:02X}")


def dump_map_region(data, offset, size=256):
    """Hex dump a region of the map data."""
    end = min(offset + size, len(data))
    for i in range(offset, end, 16):
        hex_str = ' '.join(f'{data[j]:02X}' for j in range(i, min(i + 16, end)))
        ascii_str = ''.join(
            chr(b) if 32 <= b < 127 else '.'
            for b in data[i:min(i + 16, end)]
        )
        print(f"  {i:05X}: {hex_str:<48s}  {ascii_str}")


def render_map_ascii(data, width=200, height=100):
    """Render map data as ASCII art using terrain value mapping."""
    size = len(data)
    chars = ' .:-=+*#%@'

    # Determine dimensions: try common widths
    # The map is accessed linearly, so we try various row widths
    best_width = width
    for w in [200, 304, 320, 400, 500]:
        if size % w < 10:
            best_width = w
            break

    actual_height = (size + best_width - 1) // best_width
    print(f"Rendering map as {best_width} x {actual_height} (scale: {best_width//width}:1)")

    # Scale down for display
    x_step = max(1, best_width // width)
    y_step = max(1, actual_height // height)

    for y in range(0, actual_height, y_step):
        line = []
        for x in range(0, best_width, x_step):
            idx = y * best_width + x
            if idx < size:
                val = data[idx]
                # Map terrain values to characters
                if val == 0:
                    c = ' '
                elif val <= 4:
                    c = '.'
                elif val <= 8:
                    c = ':'
                elif val <= 0x10:
                    c = '-'
                elif val <= 0x20:
                    c = '='
                elif val <= 0x30:
                    c = '+'
                elif val <= 0x40:
                    c = '*'
                else:
                    c = '#'
                line.append(c)
        print(''.join(line))


def detect_map_width(size: int) -> int:
    """Auto-detect the map row width.

    Tries 200/304/320/400/500 in order and returns the first that divides the
    data size with remainder < 10 (the same heuristic as --render). Falls back
    to 0x140 (320) when none fit.
    """
    for w in MAP_RENDER_WIDTHS:
        if size % w < 10:
            return w
    return MAP_DEFAULT_WIDTH


def map_heatmap_color(val: int) -> tuple:
    """Map a terrain byte (0x00-0xFF) to an (R, G, B) heatmap color.

    Deterministic 256-entry gradient running low->high:
      - 0x00-0x3F  black -> blue          (deep sand / lowest values)
      - 0x40-0x7F  blue  -> green         (low-mid terrain)
      - 0x80-0xBF  green -> yellow        (mid-high terrain)
      - 0xC0-0xFF  yellow -> red -> white (rock / highest values)
    Each band linearly interpolates between its two anchor colors so that
    the full 0x00..0xFF range spans black/blue (low) to red/white (high).
    """
    if val < 0x40:
        # black (0,0,0) -> blue (0,0,255)
        t = val / 0x3F
        return (0, 0, int(255 * t))
    if val < 0x80:
        # blue (0,0,255) -> green (0,255,0)
        t = (val - 0x40) / 0x3F
        return (0, int(255 * t), int(255 * (1 - t)))
    if val < 0xC0:
        # green (0,255,0) -> yellow (255,255,0)
        t = (val - 0x80) / 0x3F
        return (int(255 * t), 255, 0)
    # yellow (255,255,0) -> red (255,0,0) -> white (255,255,255)
    t = (val - 0xC0) / 0x3F
    if t < 0.5:
        # yellow -> red: drop green
        u = t / 0.5
        return (255, int(255 * (1 - u)), 0)
    # red -> white: raise green and blue
    u = (t - 0.5) / 0.5
    return (255, int(255 * u), int(255 * u))


def render_map_png(data: bytes, outpath: str, width: int = None) -> tuple:
    """Render raw MAP bytes to an indexed heatmap PNG.

    v1 heatmap: map bytes are laid out row-major at width W (auto-detected like
    --render: the first of 200/304/320/400/500 whose remainder against the data
    size is < 10, else 320, unless overridden via ``width``). Each terrain byte
    is mapped to an RGB color via the fixed :func:`map_heatmap_color` gradient
    (low = black/blue sand, mid = green/yellow, high = red/white rock). The final
    partial row is padded with black (0, 0, 0) so the RGB buffer is exactly
    width*height*3 bytes.

    Returns the chosen (width, height).
    """
    size = len(data)
    w = width if width else detect_map_width(size)
    h = (size + w - 1) // w  # round up to cover the final partial row

    # Precompute the 256-entry palette once.
    palette = [map_heatmap_color(v) for v in range(256)]

    rgb = bytearray(w * h * 3)  # zero-initialised => black padding on tail
    j = 0
    for b in data:
        r, g, bl = palette[b]
        rgb[j] = r
        rgb[j + 1] = g
        rgb[j + 2] = bl
        j += 3

    with open(outpath, 'wb') as f:
        f.write(encode_png(w, h, bytes(rgb)))
    return (w, h)


def main():
    parser = argparse.ArgumentParser(description='Dune 1992 MAP.HSQ Decoder')
    parser.add_argument('file', help='MAP.HSQ file')
    parser.add_argument('--raw', action='store_true',
                        help='Input is already decompressed')
    parser.add_argument('--stats', action='store_true',
                        help='Show map statistics and value distribution')
    parser.add_argument('--hex', type=str, metavar='OFFSET',
                        help='Hex dump at offset (decimal or 0x hex)')
    parser.add_argument('--render', action='store_true',
                        help='ASCII art rendering of map data')
    parser.add_argument('--png', type=str, metavar='FILE', default=None,
                        help='Render map bytes to a heatmap PNG file. v1 heatmap: '
                             'bytes laid out row-major at width W (auto-detected '
                             'like --render: first of 200/304/320/400/500 dividing '
                             'the size, else 320; override with --png-width); each '
                             'terrain byte -> RGB via a fixed gradient '
                             '(low=black/blue sand, mid=green/yellow, high=red/white '
                             'rock). Final partial row padded with black.')
    parser.add_argument('--png-width', type=int, default=None, metavar='W',
                        help='Override the auto-detected PNG row width')
    parser.add_argument('--width', type=int, default=120,
                        help='ASCII render width (default: 120)')
    parser.add_argument('--height', type=int, default=60,
                        help='ASCII render height (default: 60)')
    args = parser.parse_args()

    raw = open(args.file, 'rb').read()
    if args.raw:
        data = raw
    else:
        data = hsq_decompress(raw)

    if len(data) != RES_MAP_SIZE:
        print(f"Warning: expected {RES_MAP_SIZE} bytes, got {len(data)}",
              file=sys.stderr)

    if args.stats:
        analyze_map(data)
        return 0

    if args.hex:
        offset = int(args.hex, 0)
        dump_map_region(data, offset)
        return 0

    if args.render:
        render_map_ascii(data, args.width, args.height)
        return 0

    if args.png:
        w, h = render_map_png(data, args.png, args.png_width)
        print(f"Wrote heatmap PNG {args.png}: {w} x {h}")
        return 0

    # Default: brief summary
    unique = len(set(data))
    hist = {}
    for b in data:
        hist[b] = hist.get(b, 0) + 1
    top3 = sorted(hist.items(), key=lambda x: -x[1])[:3]
    print(f"MAP.HSQ: {len(data)} bytes, {unique} unique values")
    print(f"  Most common: {', '.join(f'0x{v:02X} ({c} times, {c*100//len(data)}%)' for v,c in top3)}")
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
