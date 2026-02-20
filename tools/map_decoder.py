#!/usr/bin/env python3
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

RES_MAP_SIZE = 0x0C5F9  # 50681 bytes


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
