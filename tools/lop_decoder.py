#!/usr/bin/env python3
"""
Dune 1992 LOP Background Animation Decoder

Decodes looping background animation files used for location scenes.

LOP files contain 4 animation sections (likely time-of-day phases:
dawn, day, dusk, night) that overlay the base SAL scene background.

File structure:
  File header (24 bytes):
    uint16 LE  header_size (always 0x0018 = 24)
    uint16 LE  marker (always 0xFFFF)
    uint32 LE  section_0_offset (always 0, relative to header end)
    uint32 LE  section_1_offset
    uint32 LE  section_2_offset
    uint32 LE  section_3_offset

  Section structure (per section):
    uint16 LE  section_size (total bytes including this field)
    byte       x_offset (blit X position on 320×200 screen)
    byte       y_offset (blit Y position)
    byte       width (blit width in pixels)
    byte       mode (0xFE=254: opaque, 0xFF=255: transparent-zero)
    byte       flags (bit 7: PackBits compressed)
    byte       height (blit height in pixels)
    byte       reserved (always 0x00)
    uint16 LE  data_size (= section_size - 6)
    byte[]     compressed pixel data (PackBits RLE)

  PackBits compression (same as blitGraphics in ScummVM/OpenRakis):
    Per scanline, w pixels:
      cmd & 0x80: RLE — repeat next byte (257 - cmd) times
      else:       literal — copy (cmd + 1) bytes as-is

LOP files in the game:
  MNT1.LOP - Mountain sietch type 1 (small, ~38KB)
  MNT2.LOP - Mountain sietch type 2 (small, ~38KB)
  MNT3.LOP - Mountain sietch type 3 (large, ~58KB)
  MNT4.LOP - Mountain sietch type 4 (large, ~58KB)
  PALACE.LOP - Arrakeen Palace (~35KB)
  SIET.LOP - Generic sietch (~36KB)

Usage:
  python3 lop_decoder.py gamedata/MNT1.LOP          # Analyze single file
  python3 lop_decoder.py gamedata/*.LOP --stats      # Summary of all files
  python3 lop_decoder.py gamedata/MNT1.LOP --section 0  # Detail one section
  python3 lop_decoder.py gamedata/MNT1.LOP --export DIR  # Export decoded PPM
"""

import argparse
import os
import struct
import sys


# =============================================================================
# LOP FILE PARSER
# =============================================================================

SECTION_COUNT = 4
FILE_HEADER_SIZE = 24  # 2 + 2 + 4*4 = 24

SECTION_NAMES = {
    0: "Dawn/Phase 0",
    1: "Day/Phase 1",
    2: "Dusk/Phase 2",
    3: "Night/Phase 3",
}


def parse_lop_header(data: bytes) -> dict:
    """Parse LOP file header. Returns dict with header_size, marker, section_offsets."""
    if len(data) < FILE_HEADER_SIZE:
        raise ValueError(f"File too small ({len(data)} bytes, need {FILE_HEADER_SIZE})")

    header_size = struct.unpack_from('<H', data, 0)[0]
    marker = struct.unpack_from('<H', data, 2)[0]

    if header_size != FILE_HEADER_SIZE:
        print(f"Warning: header_size={header_size}, expected {FILE_HEADER_SIZE}", file=sys.stderr)
    if marker != 0xFFFF:
        print(f"Warning: marker=0x{marker:04X}, expected 0xFFFF", file=sys.stderr)

    offsets = [struct.unpack_from('<I', data, 4 + i * 4)[0] for i in range(SECTION_COUNT)]

    return {
        'header_size': header_size,
        'marker': marker,
        'section_offsets': offsets,
    }


def parse_section(data: bytes, file_header_size: int, sec_offset: int,
                  next_offset: int, file_size: int) -> dict:
    """Parse a single LOP section."""
    abs_start = file_header_size + sec_offset
    abs_end = file_header_size + next_offset if next_offset is not None else file_size

    if abs_start >= len(data) or abs_end > len(data):
        return {'error': 'Section out of bounds'}

    sec_data = data[abs_start:abs_end]
    actual_size = len(sec_data)

    if actual_size < 11:
        return {'error': f'Section too small ({actual_size} bytes)'}

    stored_size = struct.unpack_from('<H', sec_data, 0)[0]
    x_offset = sec_data[2]
    y_offset = sec_data[3]
    width = sec_data[4]
    mode = sec_data[5]
    flags = sec_data[6]
    height = sec_data[7]
    reserved = sec_data[8]
    data_size = struct.unpack_from('<H', sec_data, 9)[0]

    compressed = (flags & 0x80) != 0
    pixel_data = sec_data[11:]

    return {
        'abs_start': abs_start,
        'abs_end': abs_end,
        'actual_size': actual_size,
        'stored_size': stored_size,
        'x_offset': x_offset,
        'y_offset': y_offset,
        'width': width,
        'height': height,
        'mode': mode,
        'flags': flags,
        'compressed': compressed,
        'reserved': reserved,
        'data_size': data_size,
        'pixel_data': pixel_data,
        'pixel_area': width * height,
    }


def decode_packbits(pixel_data: bytes, width: int, height: int, mode: int = 254) -> bytearray:
    """Decode PackBits compressed pixel data to raw pixels.

    Returns bytearray of width*height palette indices.
    Mode 255 means color 0 is transparent (preserved as 0 in output).
    """
    pixels = bytearray(width * height)
    pos = 0
    out_pos = 0
    target = width * height

    while pos < len(pixel_data) and out_pos < target:
        cmd = pixel_data[pos]
        pos += 1

        if cmd & 0x80:
            # RLE: repeat next byte (257 - cmd) times
            count = 257 - cmd
            if pos >= len(pixel_data):
                break
            val = pixel_data[pos]
            pos += 1
            for _ in range(count):
                if out_pos < target:
                    pixels[out_pos] = val
                    out_pos += 1
        else:
            # Literal: copy (cmd + 1) bytes
            count = cmd + 1
            for _ in range(count):
                if pos >= len(pixel_data) or out_pos >= target:
                    break
                pixels[out_pos] = pixel_data[pos]
                out_pos += 1
                pos += 1

    return pixels


def decode_section_pixels(section: dict) -> bytearray:
    """Decode a section's pixel data using PackBits compression."""
    return decode_packbits(
        section['pixel_data'],
        section['width'],
        section['height'],
        section['mode']
    )


# =============================================================================
# DISPLAY MODES
# =============================================================================

def show_file(filepath: str, data: bytes, verbose: bool = False):
    """Analyze a single LOP file."""
    fname = os.path.basename(filepath)
    header = parse_lop_header(data)

    print(f"=== {fname} ({len(data):,} bytes) ===")
    print(f"  Header: size={header['header_size']}, marker=0x{header['marker']:04X}")

    for si in range(SECTION_COUNT):
        offset = header['section_offsets'][si]
        next_off = header['section_offsets'][si + 1] if si + 1 < SECTION_COUNT else None
        sec = parse_section(data, header['header_size'], offset, next_off, len(data))

        if 'error' in sec:
            print(f"  Section {si} ({SECTION_NAMES[si]}): {sec['error']}")
            continue

        comp_str = 'compressed' if sec['compressed'] else 'raw'
        mode_str = 'opaque' if sec['mode'] == 254 else 'transparent' if sec['mode'] == 255 else f'0x{sec["mode"]:02X}'
        ratio = sec['actual_size'] / sec['pixel_area'] if sec['pixel_area'] > 0 else 0

        print(f"\n  Section {si} ({SECTION_NAMES[si]}):")
        print(f"    File offset: 0x{sec['abs_start']:04X}-0x{sec['abs_end']:04X}")
        print(f"    Size:        {sec['actual_size']:,} bytes (stored: {sec['stored_size']:,})")
        print(f"    Blit region: x={sec['x_offset']}, y={sec['y_offset']}, "
              f"w={sec['width']}, h={sec['height']} ({sec['pixel_area']:,} pixels)")
        print(f"    Mode:        {mode_str}, flags=0x{sec['flags']:02X} ({comp_str})")
        print(f"    Data size:   {sec['data_size']:,} (pixel data: {len(sec['pixel_data']):,} bytes)")
        print(f"    Comp. ratio: {ratio:.2f}")

        if verbose:
            # Try to decode and show stats
            pixels = decode_section_pixels(sec)
            decoded_count = sum(1 for p in pixels if p != 0)
            unique_colors = len(set(pixels))
            print(f"    Decoded:     {len(pixels):,} pixels, {unique_colors} unique colors")
            print(f"    Non-zero:    {decoded_count:,} pixels ({decoded_count*100//len(pixels)}%)")


def show_section(filepath: str, data: bytes, sec_idx: int):
    """Show detailed analysis of a single section."""
    header = parse_lop_header(data)
    offset = header['section_offsets'][sec_idx]
    next_off = header['section_offsets'][sec_idx + 1] if sec_idx + 1 < SECTION_COUNT else None
    sec = parse_section(data, header['header_size'], offset, next_off, len(data))

    if 'error' in sec:
        print(f"Section {sec_idx}: {sec['error']}")
        return

    fname = os.path.basename(filepath)
    print(f"=== {fname} Section {sec_idx} ({SECTION_NAMES[sec_idx]}) ===")
    print(f"  Blit: ({sec['x_offset']},{sec['y_offset']}) {sec['width']}x{sec['height']}")
    print(f"  Size: {sec['actual_size']:,} bytes")

    # Hex dump first 64 bytes
    print(f"\n  Raw header + first data bytes:")
    raw = data[sec['abs_start']:sec['abs_start'] + 64]
    for i in range(0, min(64, len(raw)), 16):
        hex_str = ' '.join(f'{raw[j]:02X}' for j in range(i, min(i + 16, len(raw))))
        print(f"    {i:04X}: {hex_str}")

    # Decode and analyze compression
    pixels = decode_section_pixels(sec)
    unique_colors = sorted(set(pixels))
    non_zero = sum(1 for p in pixels if p != 0)

    print(f"\n  Decoded pixels: {len(pixels):,}")
    print(f"  Non-zero:       {non_zero:,} ({non_zero*100//max(1,len(pixels))}%)")
    print(f"  Unique colors:  {len(unique_colors)}")
    if len(unique_colors) <= 32:
        print(f"  Color values:   {', '.join(f'0x{c:02X}' for c in unique_colors)}")

    # Show color histogram (top 10)
    hist = {}
    for p in pixels:
        hist[p] = hist.get(p, 0) + 1
    print(f"\n  Top 10 colors:")
    for val, count in sorted(hist.items(), key=lambda x: -x[1])[:10]:
        pct = count * 100 / len(pixels)
        bar = '#' * min(30, int(pct))
        print(f"    0x{val:02X}: {count:6d} ({pct:5.1f}%) {bar}")


def show_stats(filepaths: list):
    """Show summary statistics for multiple LOP files."""
    print(f"{'File':<14} {'Size':>8}  {'Blit':>11}  {'Sec0':>6}  {'Sec1':>6}  {'Sec2':>6}  {'Sec3':>6}")
    print('-' * 70)

    for filepath in filepaths:
        data = open(filepath, 'rb').read()
        fname = os.path.basename(filepath)
        header = parse_lop_header(data)

        sizes = []
        blit = ""
        for si in range(SECTION_COUNT):
            offset = header['section_offsets'][si]
            next_off = header['section_offsets'][si + 1] if si + 1 < SECTION_COUNT else None
            sec = parse_section(data, header['header_size'], offset, next_off, len(data))
            if 'error' not in sec:
                sizes.append(sec['actual_size'])
                if not blit:
                    blit = f"{sec['width']}x{sec['height']}@{sec['x_offset']},{sec['y_offset']}"
            else:
                sizes.append(0)

        size_strs = [f'{s:6,}' for s in sizes]
        print(f"{fname:<14} {len(data):>8,}  {blit:>11}  {'  '.join(size_strs)}")


def export_section_ppm(sec: dict, pixels: bytearray, outpath: str):
    """Write decoded section as a greyscale PPM image."""
    w, h = sec['width'], sec['height']
    if w == 0 or h == 0:
        return False

    with open(outpath, 'wb') as f:
        f.write(f'P6\n{w} {h}\n255\n'.encode())
        for p in pixels:
            # Greyscale — actual palette mapping would need the scene palette
            f.write(bytes([p, p, p]))
    return True


def export_sections(filepath: str, data: bytes, outdir: str):
    """Export all sections as PPM images."""
    os.makedirs(outdir, exist_ok=True)
    header = parse_lop_header(data)
    fname = os.path.splitext(os.path.basename(filepath))[0]
    exported = 0

    for si in range(SECTION_COUNT):
        offset = header['section_offsets'][si]
        next_off = header['section_offsets'][si + 1] if si + 1 < SECTION_COUNT else None
        sec = parse_section(data, header['header_size'], offset, next_off, len(data))

        if 'error' in sec:
            print(f"  Section {si}: {sec['error']}", file=sys.stderr)
            continue

        pixels = decode_section_pixels(sec)
        outpath = os.path.join(outdir, f'{fname}_sec{si}.ppm')
        if export_section_ppm(sec, pixels, outpath):
            exported += 1
            print(f"  Section {si}: {outpath}")

    print(f"Exported {exported}/{SECTION_COUNT} sections to {outdir}/")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 LOP Background Animation Decoder',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('files', nargs='+', help='LOP file(s)')
    p.add_argument('--section', type=int, default=None, metavar='N',
                   help='Show detailed analysis of section N (0-3)')
    p.add_argument('--stats', action='store_true',
                   help='Show summary statistics for all files')
    p.add_argument('--verbose', '-v', action='store_true',
                   help='Show decoded pixel statistics')
    p.add_argument('--export', metavar='DIR',
                   help='Export decoded sections as PPM images')
    args = p.parse_args()

    if args.stats:
        show_stats(args.files)
        return 0

    for filepath in args.files:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}", file=sys.stderr)
            continue

        data = open(filepath, 'rb').read()

        if args.section is not None:
            if args.section < 0 or args.section >= SECTION_COUNT:
                print(f"Section {args.section} out of range (0-{SECTION_COUNT-1})",
                      file=sys.stderr)
                return 1
            show_section(filepath, data, args.section)
        elif args.export:
            export_sections(filepath, data, args.export)
        else:
            show_file(filepath, data, args.verbose)

        print()

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
