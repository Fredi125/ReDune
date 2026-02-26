#!/usr/bin/env python
"""
Dune 1992 BIN File Decoder
=============================
Decode the various .BIN data files used by DNCDPRG.EXE.

Supported files:
  DNCHAR.BIN   — Font bitmap data (256 chars × 9 bytes, 8×9 mono)
  DNCHAR2.BIN  — Alternate font (Fremen/Dutch language variant)
  TABLAT.BIN   — Globe latitude lookup table (99 × 8-byte records)
  VER.BIN      — Intro/version screen vertex animation paths
  THE_END.BIN  — Identity palette remap table (2048 × uint16)

Format details:

DNCHAR.BIN / DNCHAR2.BIN (2304 bytes):
  File loaded to DS:0CEECh. Bitmap pointer word_219C4 = 0CFECh = 0CEECh + 256.
  Layout:
    Bytes 0-255:    Character width table (256 entries, 1 byte each, values 2-8)
    Bytes 256-2303: Bitmap data (up to 227 chars × 9 bytes, 8×9 mono)
  Each character bitmap: 9 bytes = 9 rows of 8 pixels (MSB = leftmost).
  Height is always 9 pixels (from ASM: CH=9 in sub_1D096).
  Index calculation: char_code × 9 + 256 (from ASM: shl×8 + add = ×9, base=0CFECh).
  DNCHAR2.BIN is used when language_setting == 6 (Fremen/Dutch).

TABLAT.BIN (792 bytes):
  99 records × 8 bytes each = latitude lookup table for globe/map view.
  Record format (from globe rendering code):
    uint16 LE: latitude angle (scaled fixed-point, ×0x18E increments)
    byte:      Y coordinate or height parameter
    byte:      scale factor or radius
    byte:      flags (0x00 or 0x01)
    byte:      secondary parameter
    2 bytes:   padding or additional data

VER.BIN (1532 bytes):
  Vertex/path data for intro version screen animations.
  Header: 5 × uint16 LE (metadata: type, frame_count, special offsets).
  Then: offset table of uint16 LE pointers to 13-byte vertex groups.
  Each vertex group: 4 × (index, x, y) coordinates + terminator byte.
  Used alongside VER.HSQ sprite sheet (resource 0x39).

THE_END.BIN (4096 bytes):
  Identity palette remap table: 2048 sequential uint16 LE values (0-2047).
  Used for ending sequence frame buffer operations.
  May be overwritten at runtime with actual remap data.

Usage:
  python bin_decoder.py DNCHAR.BIN              # Decode font
  python bin_decoder.py DNCHAR.BIN --char 65    # Show single character (A)
  python bin_decoder.py TABLAT.BIN              # Decode latitude table
  python bin_decoder.py VER.BIN                 # Decode vertex paths
  python bin_decoder.py THE_END.BIN             # Decode remap table
  python bin_decoder.py DNCHAR.BIN --render     # ASCII-art render of font
"""

import struct
import sys
import argparse
import os


# =============================================================================
# DNCHAR FONT DECODER
# =============================================================================

DNCHAR_WIDTH_OFFSET = 0       # 256-byte width table at start
DNCHAR_BITMAP_OFFSET = 256    # Bitmap data starts at byte 256 (word_219C4 = 0CFECh)
DNCHAR_CHAR_SIZE = 9          # 9 bytes per character (9 rows × 8 pixels)
DNCHAR_MAX_CHARS = 227        # (2304 - 256) // 9 = 227 complete characters


def decode_dnchar(data: bytes) -> list:
    """
    Decode DNCHAR.BIN font data (width table + bitmaps).

    Returns list of character dicts, each with:
      index: int (0-255)
      width: int (pixel width from embedded table)
      rows: list of 9 ints (bitmap rows, MSB = leftmost pixel)
    """
    if len(data) != 2304:
        raise ValueError(f"DNCHAR file should be 2304 bytes, got {len(data)}")

    chars = []
    for i in range(256):
        width = data[DNCHAR_WIDTH_OFFSET + i]
        base = DNCHAR_BITMAP_OFFSET + i * DNCHAR_CHAR_SIZE
        if base + DNCHAR_CHAR_SIZE <= len(data):
            rows = list(data[base:base + DNCHAR_CHAR_SIZE])
        else:
            rows = [0] * DNCHAR_CHAR_SIZE  # Past end of file
        chars.append({"index": i, "width": width, "rows": rows})

    return chars


def render_char(char_data: dict, marker: str = "#", blank: str = ".") -> list:
    """Render a character bitmap as ASCII art lines."""
    lines = []
    for row_byte in char_data["rows"]:
        line = ""
        for bit in range(7, -1, -1):
            line += marker if (row_byte >> bit) & 1 else blank
        lines.append(line)
    return lines


def show_dnchar(data: bytes, char_idx: int = None, do_render: bool = False):
    """Display DNCHAR font data."""
    chars = decode_dnchar(data)
    print(f"=== DNCHAR Font: 256 widths + bitmaps (9 rows × 8px) ===\n")

    if char_idx is not None:
        if 0 <= char_idx < 256:
            ch = chars[char_idx]
            label = chr(char_idx) if 32 <= char_idx < 127 else "."
            print(f"Character {char_idx} ('{label}') width={ch['width']}:")
            print(f"  Hex rows: {' '.join(f'{r:02X}' for r in ch['rows'])}")
            for line in render_char(ch):
                print(f"  {line}")
        else:
            print(f"Character index {char_idx} out of range (0-255)")
        return

    # Summary
    non_empty = sum(1 for ch in chars
                    if ch["index"] < DNCHAR_MAX_CHARS and any(r != 0 for r in ch["rows"]))
    print(f"  Characters with bitmap data: {DNCHAR_MAX_CHARS}")
    print(f"  Non-empty glyphs: {non_empty}\n")

    if do_render:
        # Render printable ASCII in grid
        cols = 16
        for row_start in range(32, 128, cols):
            row_end = min(row_start + cols, 128)
            # Header with widths
            header = "     " + "".join(
                f"{'%s(%d)' % (chr(c), chars[c]['width']):>10s}"
                for c in range(row_start, row_end))
            print(header)

            # Render all 9 rows
            for pixel_row in range(9):
                line = f"  {pixel_row}: "
                for c in range(row_start, row_end):
                    byte_val = chars[c]["rows"][pixel_row]
                    w = chars[c]["width"]
                    bits = ""
                    for bit in range(7, -1, -1):
                        bits += "#" if (byte_val >> bit) & 1 else " "
                    line += f" {bits} "
                print(line)
            print()
    else:
        # Compact display with widths
        print(f"  Printable ASCII widths and glyphs:")
        for i in range(32, 128, 8):
            line_parts = []
            for j in range(i, min(i + 8, 128)):
                ch = chars[j]
                label = chr(j) if 32 <= j < 127 else "."
                has_data = any(r != 0 for r in ch["rows"])
                line_parts.append(f"'{label}'w={ch['width']}")
            print(f"  [{i:3d}] {' '.join(line_parts)}")


# =============================================================================
# TABLAT LATITUDE TABLE DECODER
# =============================================================================

def decode_tablat(data: bytes) -> list:
    """
    Decode TABLAT.BIN latitude lookup table.

    Returns list of 99 records, each with:
      index, lat_angle, y_param, scale, flags, secondary, extra
    """
    if len(data) != 792:
        raise ValueError(f"TABLAT file should be 792 bytes, got {len(data)}")

    records = []
    for i in range(99):
        base = i * 8
        lat_angle = struct.unpack_from('<H', data, base)[0]
        y_param = data[base + 2]
        scale = data[base + 3]
        flags = data[base + 4]
        secondary = data[base + 5]
        extra = struct.unpack_from('<H', data, base + 6)[0]

        records.append({
            "index": i,
            "lat_angle": lat_angle,
            "y_param": y_param,
            "scale": scale,
            "flags": flags,
            "secondary": secondary,
            "extra": extra,
        })

    return records


def show_tablat(data: bytes):
    """Display TABLAT latitude table."""
    records = decode_tablat(data)
    print(f"=== TABLAT: Globe Latitude Table (99 × 8 bytes) ===\n")
    print(f"  {'Idx':>3s}  {'LatAngle':>8s}  {'Y':>3s}  {'Scale':>5s}  "
          f"{'Flags':>5s}  {'Sec':>3s}  {'Extra':>5s}")
    print(f"  {'---':>3s}  {'--------':>8s}  {'---':>3s}  {'-----':>5s}  "
          f"{'-----':>5s}  {'---':>3s}  {'-----':>5s}")

    for r in records:
        print(f"  {r['index']:3d}  0x{r['lat_angle']:04X}  "
              f"{r['y_param']:3d}  0x{r['scale']:02X}   "
              f"0x{r['flags']:02X}   {r['secondary']:3d}  "
              f"0x{r['extra']:04X}")


# =============================================================================
# VER.BIN VERTEX PATH DECODER
# =============================================================================

def decode_ver(data: bytes) -> dict:
    """
    Decode VER.BIN vertex animation path data.

    Returns dict with header info and vertex groups.
    """
    if len(data) < 10:
        raise ValueError("VER.BIN too short")

    # Header: 5 × uint16
    header = struct.unpack_from('<5H', data, 0)

    # Read offset table (uint16 values from byte 10 onwards)
    # Offsets in the regular section start at index 5 and are 13-byte spaced
    offsets = []
    pos = 0
    while pos + 2 <= len(data):
        off = struct.unpack_from('<H', data, pos)[0]
        if off >= len(data):
            break
        offsets.append(off)
        pos += 2
        # Stop when we reach the first data offset
        if pos >= off and off > 0:
            break

    # The first data starts at the smallest non-zero offset
    non_zero = [o for o in offsets if o > 0]
    if non_zero:
        data_start = min(non_zero)
    else:
        data_start = 10

    # Parse offset table properly
    n_offsets = data_start // 2
    all_offsets = []
    for i in range(n_offsets):
        off = struct.unpack_from('<H', data, i * 2)[0]
        all_offsets.append(off)

    # Parse vertex groups at each offset
    groups = []
    for i, off in enumerate(all_offsets):
        if off >= len(data):
            continue
        # Determine end of this group
        next_off = len(data)
        for j in range(i + 1, len(all_offsets)):
            if all_offsets[j] > off:
                next_off = all_offsets[j]
                break

        # Parse vertices: (index_byte, x_byte, y_byte) until 0x00 terminator
        verts = []
        pos = off
        while pos < min(next_off, len(data)):
            if data[pos] == 0x00:
                break
            if pos + 3 <= len(data):
                idx = data[pos]
                x = data[pos + 1]
                y = data[pos + 2]
                verts.append((idx, x, y))
                pos += 3
            else:
                break

        groups.append({
            "offset_idx": i,
            "file_offset": off,
            "vertices": verts,
        })

    return {
        "header": header,
        "offset_count": n_offsets,
        "groups": groups,
    }


def show_ver(data: bytes):
    """Display VER.BIN vertex path data."""
    result = decode_ver(data)
    print(f"=== VER.BIN: Intro Vertex Paths ({len(data)} bytes) ===\n")
    print(f"  Header: {', '.join(f'0x{v:04X}' for v in result['header'])}")
    print(f"  Offset table entries: {result['offset_count']}")
    print(f"  Vertex groups: {len(result['groups'])}\n")

    for g in result["groups"]:
        if g["vertices"]:
            vert_str = " ".join(f"({v[0]},{v[1]},{v[2]})" for v in g["vertices"][:6])
            if len(g["vertices"]) > 6:
                vert_str += "..."
            print(f"  [{g['offset_idx']:2d}] @0x{g['file_offset']:04X} "
                  f"{len(g['vertices']):2d} verts: {vert_str}")


# =============================================================================
# THE_END.BIN REMAP TABLE DECODER
# =============================================================================

def decode_the_end(data: bytes) -> list:
    """Decode THE_END.BIN palette remap table."""
    if len(data) != 4096:
        raise ValueError(f"THE_END.BIN should be 4096 bytes, got {len(data)}")

    values = []
    for i in range(0, len(data), 2):
        values.append(struct.unpack_from('<H', data, i)[0])
    return values


def show_the_end(data: bytes):
    """Display THE_END.BIN remap table."""
    values = decode_the_end(data)
    is_identity = all(values[i] == i for i in range(len(values)))

    print(f"=== THE_END.BIN: Palette Remap Table ({len(data)} bytes) ===\n")
    print(f"  Entries: {len(values)} × uint16 LE")
    print(f"  Range: {min(values)} - {max(values)}")
    print(f"  Identity mapping: {is_identity}")

    if not is_identity:
        # Show non-identity entries
        non_id = [(i, v) for i, v in enumerate(values) if v != i]
        print(f"  Non-identity entries: {len(non_id)}")
        for idx, val in non_id[:20]:
            print(f"    [{idx}] → {val}")
        if len(non_id) > 20:
            print(f"    ... ({len(non_id) - 20} more)")
    else:
        print(f"  (Default initialization table — all entries map to themselves)")


# =============================================================================
# AUTO-DETECT AND MAIN
# =============================================================================

FILE_HANDLERS = {
    "DNCHAR.BIN": show_dnchar,
    "DNCHAR2.BIN": show_dnchar,
    "TABLAT.BIN": show_tablat,
    "VER.BIN": show_ver,
    "THE_END.BIN": show_the_end,
}

SIZE_HANDLERS = {
    2304: show_dnchar,
    792: show_tablat,
    4096: show_the_end,
}


def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 BIN File Decoder',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file', help='BIN data file')
    p.add_argument('--char', type=int, default=None, metavar='N',
                   help='Show single font character by index (DNCHAR only)')
    p.add_argument('--render', action='store_true',
                   help='ASCII-art render of font glyphs (DNCHAR only)')
    p.add_argument('--raw', action='store_true',
                   help='Include raw hex dump')
    args = p.parse_args()

    with open(args.file, 'rb') as f:
        data = f.read()

    basename = os.path.basename(args.file).upper()
    print(f"  Loaded: {os.path.basename(args.file)} — {len(data):,} bytes\n")

    # Try filename match first
    handler = FILE_HANDLERS.get(basename)

    # Fall back to size-based detection
    if handler is None:
        handler = SIZE_HANDLERS.get(len(data))

    if handler is None:
        print(f"Unknown BIN format: {basename} ({len(data)} bytes)")
        print("Supported: DNCHAR.BIN, DNCHAR2.BIN, TABLAT.BIN, VER.BIN, THE_END.BIN")
        sys.exit(1)

    # DNCHAR handlers take extra args
    if basename in ("DNCHAR.BIN", "DNCHAR2.BIN") or len(data) == 2304:
        handler(data, char_idx=args.char, do_render=args.render)
    else:
        handler(data)

    if args.raw:
        print(f"\n  Raw hex (first 128 bytes):")
        for i in range(0, min(128, len(data)), 16):
            hex_part = ' '.join(f'{b:02X}' for b in data[i:i + 16])
            print(f"    {i:04X}: {hex_part}")


if __name__ == '__main__':
    main()
