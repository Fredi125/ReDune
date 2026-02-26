#!/usr/bin/env python
"""
Dune 1992 Sprite HSQ Decoder

Decodes sprite graphics from HSQ-compressed game resources.
Format based on OpenRakis dunespr.c (DuneSpr_GetSpriteData).

Sprite HSQ file structure (decompressed):
  - uint16 LE at offset 0: pointer to offset table (= palette end)
  - Palette data at bytes 2..first_word (VGA 6-bit color chunks)
  - Offset table at first_word: N × uint16 LE sprite offsets
  - Sprite data: 4-byte header + 4-bit bipixel data

Palette chunk format:
  start_index (byte), count (byte), count × 3 bytes (R,G,B 0-63)
  Terminator: 0xFF 0xFF

Sprite header (4 bytes):
  byte 0: width_low
  byte 1: bit7=compression, bits6-0=width_high
  byte 2: height
  byte 3: palette_offset (base color index for this sprite)
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress


def decode_palette(data, pal_end):
    """Decode VGA palette chunks from sprite file."""
    palette = {}  # index → (r, g, b) in 0-255 range
    pos = 2  # skip the uint16 offset

    while pos + 1 < pal_end:
        start_idx = data[pos]
        count = data[pos + 1]
        pos += 2

        if start_idx == 0xFF and count == 0xFF:
            break

        for i in range(count):
            if pos + 2 >= len(data):
                break
            r = data[pos] & 0x3F
            g = data[pos + 1] & 0x3F
            b = data[pos + 2] & 0x3F
            # Convert 6-bit VGA (0-63) to 8-bit (0-255)
            palette[start_idx + i] = (r * 255 // 63, g * 255 // 63, b * 255 // 63)
            pos += 3

    return palette


def count_sprites(data):
    """Count sprites in decompressed sprite file."""
    pal_end = struct.unpack_from('<H', data, 0)[0]
    offset_table = data[pal_end:]
    first_sprite_off = struct.unpack_from('<H', offset_table, 0)[0]
    return first_sprite_off // 2


def decode_sprite(data, sprite_idx):
    """Decode a single sprite from decompressed sprite file.

    Returns dict with width, height, palette_offset, compressed,
    and pixels (list of palette indices, width × height).
    """
    pal_end = struct.unpack_from('<H', data, 0)[0]
    offset_table_base = pal_end
    has_extra = (pal_end == 2)  # no palette → 2 extra header bytes

    sprite_off = struct.unpack_from('<H', data, offset_table_base + sprite_idx * 2)[0]
    sprite_base = offset_table_base + sprite_off

    pos = sprite_base
    width = data[pos]
    compression = (data[pos + 1] & 0x80) != 0
    width += (data[pos + 1] & 0x7F) << 8
    height = data[pos + 2]
    pal_offset = data[pos + 3]
    pos += 4

    if has_extra:
        pos += 2  # skip 2 unknown bytes

    if width == 0 or height == 0:
        return {
            'width': width, 'height': height,
            'palette_offset': pal_offset, 'compressed': compression,
            'pixels': []
        }

    pixels = [0] * (width * height)
    col = 0
    row = 0
    alignment = 0

    if compression:
        while row < height:
            if pos >= len(data):
                break
            rep = data[pos]
            pos += 1
            # Interpret as signed byte
            if rep >= 128:
                rep = rep - 256

            if rep < 0:
                # RLE: repeat bipixel (-rep + 1) times
                if pos >= len(data):
                    break
                bipixel = data[pos]
                pos += 1
                for _ in range(-rep + 1):
                    if col < width:
                        pixels[row * width + col] = pal_offset + (bipixel & 0x0F)
                    col += 1
                    alignment += 1
                    if col < width:
                        pixels[row * width + col] = pal_offset + (bipixel >> 4)
                    col += 1
                    alignment += 1

                if col >= width:
                    col = 0
                    row += 1
                    skip = (4 - (alignment % 4)) % 4
                    pos += skip
                    alignment = 0
            else:
                # Literal: read (rep + 1) bipixels
                for _ in range(rep + 1):
                    if pos >= len(data):
                        break
                    bipixel = data[pos]
                    pos += 1
                    if col < width:
                        pixels[row * width + col] = pal_offset + (bipixel & 0x0F)
                    col += 1
                    alignment += 1
                    if col < width:
                        pixels[row * width + col] = pal_offset + (bipixel >> 4)
                    col += 1
                    alignment += 1

                if col >= width:
                    col = 0
                    row += 1
                    skip = (4 - (alignment % 4)) % 4
                    pos += skip
                    alignment = 0
    else:
        # Uncompressed: read pairs of bytes → 4 pixels
        while row < height:
            if pos + 1 >= len(data):
                break
            bipixel = data[pos]
            bipixel2 = data[pos + 1]
            pos += 2

            if col < width:
                pixels[row * width + col] = pal_offset + (bipixel & 0x0F)
            col += 1
            if col < width:
                pixels[row * width + col] = pal_offset + (bipixel >> 4)
            col += 1
            if col < width:
                pixels[row * width + col] = pal_offset + (bipixel2 & 0x0F)
            col += 1
            if col < width:
                pixels[row * width + col] = pal_offset + (bipixel2 >> 4)
            col += 1

            if col >= width:
                col = 0
                row += 1

    return {
        'width': width,
        'height': height,
        'palette_offset': pal_offset,
        'compressed': compression,
        'pixels': pixels
    }


def sprite_to_ppm(sprite, palette, outpath):
    """Write sprite as PPM image file."""
    w, h = sprite['width'], sprite['height']
    if w == 0 or h == 0:
        return False

    with open(outpath, 'wb') as f:
        f.write(f'P6\n{w} {h}\n255\n'.encode())
        for idx in sprite['pixels']:
            if idx in palette:
                r, g, b = palette[idx]
            else:
                r = g = b = 0  # unmapped → black
            f.write(bytes([r, g, b]))
    return True


def main():
    parser = argparse.ArgumentParser(description='Dune 1992 Sprite HSQ Decoder')
    parser.add_argument('file', help='Sprite HSQ file (e.g. CHAN.HSQ)')
    parser.add_argument('--raw', action='store_true',
                        help='Input is already decompressed')
    parser.add_argument('--sprite', type=int, metavar='N',
                        help='Show single sprite by index')
    parser.add_argument('--stats', action='store_true',
                        help='Show file statistics')
    parser.add_argument('--export', metavar='DIR',
                        help='Export sprites as PPM images to directory')
    parser.add_argument('--ascii', type=int, metavar='N',
                        help='ASCII-art preview of sprite N')
    args = parser.parse_args()

    raw = open(args.file, 'rb').read()
    if args.raw:
        data = raw
    else:
        data = hsq_decompress(raw)

    if len(data) < 4:
        print("Error: file too small", file=sys.stderr)
        return 1

    pal_end = struct.unpack_from('<H', data, 0)[0]
    has_palette = (pal_end > 2)
    n_sprites = count_sprites(data)
    palette = decode_palette(data, pal_end) if has_palette else {}

    basename = os.path.splitext(os.path.basename(args.file))[0]

    if args.stats:
        print(f"File: {args.file}")
        print(f"  Compressed:   {len(raw)} bytes")
        print(f"  Decompressed: {len(data)} bytes")
        print(f"  Palette end:  0x{pal_end:04X} ({'has palette' if has_palette else 'no palette'})")
        print(f"  Palette colors: {len(palette)}")
        print(f"  Sprite count: {n_sprites}")
        print()

        # Show sprite summary table
        print(f"  {'Idx':>4}  {'Width':>5}  {'Height':>6}  {'PalOff':>6}  {'Compressed':>10}")
        print(f"  {'-'*4}  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*10}")
        for i in range(n_sprites):
            try:
                spr = decode_sprite(data, i)
                comp_str = 'RLE' if spr['compressed'] else 'raw'
                print(f"  {i:4d}  {spr['width']:5d}  {spr['height']:6d}  "
                      f"0x{spr['palette_offset']:02X}    {comp_str:>10}")
            except Exception as e:
                print(f"  {i:4d}  ERROR: {e}")
        return 0

    if args.sprite is not None:
        if args.sprite >= n_sprites:
            print(f"Error: sprite {args.sprite} out of range (0-{n_sprites-1})",
                  file=sys.stderr)
            return 1
        spr = decode_sprite(data, args.sprite)
        print(f"Sprite {args.sprite}:")
        print(f"  Size: {spr['width']} x {spr['height']}")
        print(f"  Palette offset: 0x{spr['palette_offset']:02X}")
        print(f"  Compressed: {'RLE' if spr['compressed'] else 'raw'}")
        return 0

    if args.ascii is not None:
        if args.ascii >= n_sprites:
            print(f"Error: sprite {args.ascii} out of range (0-{n_sprites-1})",
                  file=sys.stderr)
            return 1
        spr = decode_sprite(data, args.ascii)
        w, h = spr['width'], spr['height']
        print(f"Sprite {args.ascii}: {w}x{h}, pal_offset=0x{spr['palette_offset']:02X}")
        if w == 0 or h == 0:
            print("  (empty sprite)")
            return 0
        # ASCII art: map pixel values to density characters
        chars = " .:-=+*#%@"
        pal_off = spr['palette_offset']
        for y in range(min(h, 60)):  # limit height
            line = []
            # Sample every other pixel for width
            step = max(1, w // 80)
            for x in range(0, w, step):
                idx = spr['pixels'][y * w + x]
                val = (idx - pal_off) & 0xFF
                c = chars[min(val, len(chars) - 1)]
                line.append(c)
            print(''.join(line))
        return 0

    if args.export:
        os.makedirs(args.export, exist_ok=True)
        exported = 0
        for i in range(n_sprites):
            try:
                spr = decode_sprite(data, i)
                outpath = os.path.join(args.export, f'{basename}_{i:03d}.ppm')
                if sprite_to_ppm(spr, palette, outpath):
                    exported += 1
            except Exception as e:
                print(f"  Sprite {i}: error: {e}", file=sys.stderr)
        print(f"Exported {exported}/{n_sprites} sprites to {args.export}/")
        return 0

    # Default: summary
    print(f"{basename}: {n_sprites} sprites, {len(palette)} palette colors, "
          f"{'has' if has_palette else 'no'} palette")
    for i in range(min(n_sprites, 20)):
        try:
            spr = decode_sprite(data, i)
            comp_str = 'RLE' if spr['compressed'] else 'raw'
            print(f"  [{i:3d}] {spr['width']:4d}x{spr['height']:<4d}  "
                  f"pal=0x{spr['palette_offset']:02X}  {comp_str}")
        except Exception as e:
            print(f"  [{i:3d}] ERROR: {e}")
    if n_sprites > 20:
        print(f"  ... ({n_sprites - 20} more sprites)")

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
