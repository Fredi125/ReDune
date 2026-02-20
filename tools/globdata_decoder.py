#!/usr/bin/env python3
"""GLOBDATA.HSQ decoder for Dune (1992, Cryo Interactive, CD v3.7).

Decodes the globe rendering data resource containing:
  Part 1: Polygon shading gradient tables (0x0000-0x0B34)
  Part 2: Globe projection scanline data (0x0B35 onward)

The RESOURCE_GLOBDATA buffer is dual-purpose:
  - Loaded from GLOBDATA.HSQ for globe rendering
  - Overwritten at runtime for map terrain histograms

Usage:
  python3 tools/globdata_decoder.py gamedata/GLOBDATA.HSQ
  python3 tools/globdata_decoder.py gamedata/GLOBDATA.HSQ --gradients
  python3 tools/globdata_decoder.py gamedata/GLOBDATA.HSQ --globe
  python3 tools/globdata_decoder.py gamedata/GLOBDATA.HSQ --globe --verbose
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress

# Globe section constants
GLOBE_BLOCK_SIZE = 200      # Each latitude scanline block
GLOBE_RAMP_SIZE = 98        # x-to-longitude mapping entries per block
GLOBE_TERRAIN_SIZE = 101    # Terrain/shade data per block (incl. 2-byte padding)
GLOBE_BLOCK_COUNT = 64      # Number of latitude scanline blocks
GLOBE_PREFIX_SIZE = 422     # Zero padding before first block


def parse_gradient_tables(data):
    """Parse Part 1: polygon shading gradient tables.

    Structure: series of variable-length tables, each starting with a marker
    byte where table_length = 256 - marker. The (length - 1) data bytes
    are incrementing color indices for gradient/shading fills.

    Used by _sub_13BE9_SAL_polygon for shaded polygon fills in SAL scenes.

    Returns (list of table dicts, end_offset).
    """
    tables = []
    i = 0
    while i < len(data):
        marker = data[i]
        if marker < 0xBF:
            break
        table_len = 256 - marker
        if table_len == 1:
            # 0xFF = single-byte entry (terminator/empty)
            tables.append({
                'offset': i,
                'marker': marker,
                'length': 0,
                'base_color': 0,
                'values': [],
            })
            i += 1
            continue
        if i + table_len > len(data):
            break
        values = list(data[i + 1:i + table_len])
        tables.append({
            'offset': i,
            'marker': marker,
            'length': len(values),
            'base_color': values[0] if values else 0,
            'values': values,
        })
        i += table_len
    return tables, i


def parse_globe_scanlines(data, globe_start):
    """Parse Part 2: globe projection scanline data.

    After the gradient tables, a prefix of zeros is followed by 64 fixed-size
    200-byte blocks. Each block represents one latitude line of the globe
    (one hemisphere; the other is mirrored).

    Block structure (200 bytes):
      Bytes 0-97:  98-byte longitude ramp (x → longitude coordinate mapping)
      Byte 98:     0x00 separator
      Bytes 99-199: 101 bytes terrain/shade data (99 values + 2 padding zeros)

    The ramp maps screen x-positions to globe longitude coordinates. At the
    equator, the mapping is nearly linear (02, 04, 06, ...). At higher
    latitudes, the values advance non-linearly due to sphere curvature,
    and the max value decreases (less longitude visible).

    Returns list of scanline dicts.
    """
    scanlines = []
    # First block starts after zero prefix
    first_block = globe_start + GLOBE_PREFIX_SIZE

    for block_idx in range(GLOBE_BLOCK_COUNT):
        block_start = first_block + block_idx * GLOBE_BLOCK_SIZE
        if block_start + GLOBE_BLOCK_SIZE > len(data):
            break

        block = data[block_start:block_start + GLOBE_BLOCK_SIZE]

        # Ramp: fixed 98 bytes
        ramp = list(block[:GLOBE_RAMP_SIZE])
        ramp_max = max(ramp) if ramp else 0

        # Check if ramp is linearly incrementing by 2
        linear = all(ramp[i] == (i + 1) * 2 for i in range(GLOBE_RAMP_SIZE))

        # Terrain: bytes 99-199 (after separator at byte 98)
        terrain = list(block[GLOBE_RAMP_SIZE + 1:GLOBE_BLOCK_SIZE])
        # Strip trailing zeros (padding)
        terrain_trimmed = terrain[:]
        while terrain_trimmed and terrain_trimmed[-1] == 0:
            terrain_trimmed.pop()

        scanlines.append({
            'index': block_idx,
            'offset': block_start,
            'ramp': ramp,
            'ramp_max': ramp_max,
            'ramp_linear': linear,
            'terrain': terrain_trimmed,
            'terrain_raw': terrain,
            'unique_terrain': len(set(terrain_trimmed)) if terrain_trimmed else 0,
        })

    return scanlines


def show_gradients(tables):
    """Display gradient table analysis."""
    # Filter out empty/terminator tables
    real_tables = [t for t in tables if t['length'] > 0]

    print(f"\n=== Part 1: Polygon Shading Gradient Tables ({len(real_tables)} tables) ===\n")
    print(f"Used by _sub_13BE9_SAL_polygon for shaded polygon fills in SAL scenes.")
    print(f"Each table: marker byte (len = 256 - marker) + color index gradient.\n")
    print(f"{'Table':>5s}  {'Offset':>6s}  {'Marker':>6s}  {'Len':>3s}  {'Base':>4s}  {'Values'}")
    print(f"{'─'*5:>5s}  {'─'*6:>6s}  {'─'*6:>6s}  {'─'*3:>3s}  {'─'*4:>4s}  {'─'*50}")

    for idx, t in enumerate(real_tables):
        vals = t['values']
        val_str = ' '.join(f'{v:02X}' for v in vals[:12])
        if len(vals) > 12:
            val_str += f' ... {vals[-1]:02X}'
        print(f"{idx:5d}  0x{t['offset']:04X}  0x{t['marker']:02X}    {t['length']:3d}  0x{t['base_color']:02X}  {val_str}")

    print(f"\n  Real tables: {len(real_tables)}")
    if real_tables:
        print(f"  Table sizes: {min(t['length'] for t in real_tables)}-{max(t['length'] for t in real_tables)} entries")
        print(f"  Base colors: 0x{min(t['base_color'] for t in real_tables):02X}-0x{max(t['base_color'] for t in real_tables):02X}")
    print(f"  Terminators: {len(tables) - len(real_tables)} empty 0xFF entries")


def show_globe(scanlines, verbose=False):
    """Display globe projection scanline analysis."""
    print(f"\n=== Part 2: Globe Projection Scanlines ({len(scanlines)} blocks) ===\n")
    print(f"64 latitude scanlines × 200 bytes. Each block: 98-byte ramp + 101-byte terrain.")
    print(f"Ramp maps screen x-position → globe longitude. Terrain = shade/type values.\n")

    print(f"{'Line':>4s}  {'Offset':>6s}  {'Max':>5s}  {'Type':>7s}  {'Terrain':>7s}  {'Uniq':>4s}  {'Visual'}")
    print(f"{'─'*4:>4s}  {'─'*6:>6s}  {'─'*5:>5s}  {'─'*7:>7s}  {'─'*7:>7s}  {'─'*4:>4s}  {'─'*52}")

    for sl in scanlines:
        # Visual: show ramp coverage proportional to max value
        visible_width = sl['ramp_max'] // 4 if sl['ramp_max'] > 0 else 0
        bar = '#' * min(visible_width, 50)
        pad = ' ' * (50 - len(bar))

        ramp_type = 'linear' if sl['ramp_linear'] else 'curved'
        terr_count = len(sl['terrain'])

        print(f"{sl['index']:4d}  0x{sl['offset']:04X}  0x{sl['ramp_max']:02X}  {ramp_type:>7s}  {terr_count:7d}  {sl['unique_terrain']:4d}  |{bar}{pad}|")

        if verbose:
            # Show ramp values (first 20 + last value)
            ramp = sl['ramp']
            ramp_str = ' '.join(f'{v:02X}' for v in ramp[:20])
            if len(ramp) > 20:
                ramp_str += f' ... {ramp[-1]:02X}'
            print(f"        ramp: [{ramp_str}]")

            # Show terrain values
            terr = sl['terrain']
            if terr:
                terr_str = ' '.join(f'{v:02X}' for v in terr[:20])
                if len(terr) > 20:
                    terr_str += f' ... {terr[-1]:02X}'
                print(f"        terr: [{terr_str}]")
            print()

    # Summary
    if scanlines:
        max_vals = [s['ramp_max'] for s in scanlines]
        linear_count = sum(1 for s in scanlines if s['ramp_linear'])
        print(f"\n  Scanlines: {len(scanlines)} (equator to pole, mirrored for other hemisphere)")
        print(f"  Ramp max range: 0x{min(max_vals):02X}-0x{max(max_vals):02X} (longitude coverage)")
        print(f"  Linear ramps: {linear_count}, curved ramps: {len(scanlines) - linear_count}")


def show_stats(data, tables, globe_start, scanlines):
    """Show overall file statistics."""
    real_tables = [t for t in tables if t['length'] > 0]
    block_start = globe_start + GLOBE_PREFIX_SIZE

    print(f"\n=== GLOBDATA.HSQ Statistics ===\n")
    print(f"  Total decompressed size: {len(data)} bytes (0x{len(data):04X})")
    print(f"  Part 1 (gradients):  0x0000-0x{globe_start-1:04X} ({globe_start} bytes)")
    print(f"  Part 2 (globe):      0x{globe_start:04X}-0x{len(data)-1:04X} ({len(data)-globe_start} bytes)")

    print(f"\n  --- Part 1: Gradient Tables ---")
    print(f"  Purpose: SAL polygon shading (_sub_13BE9_SAL_polygon)")
    print(f"  Format: marker byte (len = 256 - marker) + color index gradient")
    print(f"  Tables: {len(real_tables)} gradient + {len(tables)-len(real_tables)} terminators")
    if real_tables:
        print(f"  Sizes: {min(t['length'] for t in real_tables)}-{max(t['length'] for t in real_tables)} entries per table")
        print(f"  Base colors: 0x{min(t['base_color'] for t in real_tables):02X}-0x{max(t['base_color'] for t in real_tables):02X}")

    print(f"\n  --- Part 2: Globe Projection ---")
    print(f"  Purpose: spinning globe view (sub_1BA75 → gfx_vtable_func_29)")
    print(f"  Works with: TABLAT.BIN (latitude lookup) + MAP.HSQ (terrain)")
    print(f"  Zero prefix: {GLOBE_PREFIX_SIZE} bytes (0x{globe_start:04X}-0x{block_start-1:04X})")
    print(f"  Scanline blocks: {len(scanlines)} × {GLOBE_BLOCK_SIZE} bytes = {len(scanlines)*GLOBE_BLOCK_SIZE} bytes")
    print(f"  Block structure: {GLOBE_RAMP_SIZE}-byte ramp + 1 sep + {GLOBE_TERRAIN_SIZE}-byte terrain")
    if scanlines:
        max_vals = [s['ramp_max'] for s in scanlines]
        print(f"  Longitude range: 0x{min(max_vals):02X}-0x{max(max_vals):02X}")

    print(f"\n  --- Buffer Reuse at Runtime ---")
    print(f"  RESOURCE_GLOBDATA buffer is also used for:")
    print(f"  - Map terrain histogram (256 × uint16 LE, counts byte values in MAP.HSQ)")
    print(f"  - Overwrites loaded GLOBDATA.HSQ content (lines 386-404 in ASM)")


def main():
    parser = argparse.ArgumentParser(
        description='Decode GLOBDATA.HSQ (globe rendering data)')
    parser.add_argument('input', help='GLOBDATA.HSQ file')
    parser.add_argument('--gradients', action='store_true',
                        help='Show gradient table details')
    parser.add_argument('--globe', action='store_true',
                        help='Show globe scanline details')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed data values')
    args = parser.parse_args()

    # Read and decompress
    with open(args.input, 'rb') as f:
        raw = f.read()

    # Check if HSQ compressed
    if len(raw) >= 6:
        checksum = sum(raw[:6]) & 0xFF
        if checksum == 0xAB:
            data = hsq_decompress(raw)
            print(f"  Decompressed: {len(raw)} → {len(data)} bytes")
        else:
            data = raw
    else:
        data = raw

    # Parse both sections
    tables, globe_start = parse_gradient_tables(data)
    scanlines = parse_globe_scanlines(data, globe_start)

    # Default: show stats
    if not args.gradients and not args.globe:
        show_stats(data, tables, globe_start, scanlines)

    if args.gradients:
        show_gradients(tables)

    if args.globe:
        show_globe(scanlines, verbose=args.verbose)


if __name__ == '__main__':
    main()
