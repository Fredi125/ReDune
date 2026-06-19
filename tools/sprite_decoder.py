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
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress
from png import encode_png, encode_png_rgba


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


def sprite_to_rgb(sprite: dict, palette: dict) -> bytes:
    """Flatten a decoded sprite's pixels to a 24-bit RGB buffer.

    Mapped palette indices use their color; unmapped indices render black.
    Returns width*height*3 bytes (row-major).
    """
    buf = bytearray()
    for idx in sprite['pixels']:
        if idx in palette:
            r, g, b = palette[idx]
        else:
            r = g = b = 0  # unmapped → black
        buf += bytes((r, g, b))
    return bytes(buf)


def sprite_to_rgba(sprite: dict, palette: dict, opaque: bool = False) -> bytes:
    """Flatten a decoded sprite's pixels to a 32-bit RGBA buffer.

    Palette index 0 is treated as transparent (alpha 0) unless ``opaque`` is
    set. Mapped indices use their color (opaque); unmapped non-zero indices
    render as opaque black. Returns width*height*4 bytes (row-major).
    """
    buf = bytearray()
    for idx in sprite['pixels']:
        if idx == 0 and not opaque:
            buf += b'\x00\x00\x00\x00'  # transparent
            continue
        if idx in palette:
            r, g, b = palette[idx]
        else:
            r = g = b = 0  # unmapped → opaque black
        buf += bytes((r, g, b, 255))
    return bytes(buf)


def export_pngs(data: bytes, n_sprites: int, palette: dict, outdir: str,
                basename: str, opaque: bool = False) -> int:
    """Export each non-empty sprite as a separate RGBA PNG.

    Returns the number of PNGs written. Empty sprites (0 width/height) are
    skipped. Decode errors are reported to stderr and skipped.
    """
    os.makedirs(outdir, exist_ok=True)
    exported = 0
    for i in range(n_sprites):
        try:
            spr = decode_sprite(data, i)
        except Exception as e:
            print(f"  Sprite {i}: error: {e}", file=sys.stderr)
            continue
        w, h = spr['width'], spr['height']
        if w == 0 or h == 0:
            continue
        rgba = sprite_to_rgba(spr, palette, opaque=opaque)
        outpath = os.path.join(outdir, f'{basename}_{i:03d}.png')
        with open(outpath, 'wb') as f:
            f.write(encode_png_rgba(w, h, rgba))
        exported += 1
    return exported


def _shelf_pack(boxes: list, max_width: int) -> tuple:
    """Pack (index, w, h) boxes into shelves; return (placements, sheet_w, sheet_h).

    Simple row/shelf packer: sort by descending height, lay left-to-right,
    wrap to a new shelf when a box would exceed ``max_width``. Returns a list
    of (index, x, y, w, h) placements plus the resulting sheet dimensions.
    """
    order = sorted(boxes, key=lambda b: (-b[2], -b[1]))
    placements = []
    x = 0
    y = 0
    shelf_h = 0
    sheet_w = 0
    for idx, w, h in order:
        if x + w > max_width and x > 0:
            # Wrap to next shelf
            y += shelf_h
            x = 0
            shelf_h = 0
        placements.append((idx, x, y, w, h))
        x += w
        shelf_h = max(shelf_h, h)
        sheet_w = max(sheet_w, x)
    sheet_h = y + shelf_h
    return placements, sheet_w, sheet_h


def export_atlas(data: bytes, n_sprites: int, palette: dict, outdir: str,
                 basename: str, opaque: bool = False) -> dict:
    """Pack all non-empty sprites into one PNG sheet + a JSON atlas.

    Writes ``<basename>.png`` (the sheet) and ``<basename>.json`` (the atlas
    metadata) into ``outdir``. The atlas JSON has the schema:
      {"file": <png name>, "palette_colors": N,
       "sprites": [{"index", "x", "y", "w", "h", "palette_offset"} ...]}

    Returns the atlas dict. Sprites are shelf-packed (transparent gaps).
    """
    os.makedirs(outdir, exist_ok=True)

    # Decode all non-empty sprites up front.
    decoded = []  # (index, sprite_dict)
    for i in range(n_sprites):
        try:
            spr = decode_sprite(data, i)
        except Exception as e:
            print(f"  Sprite {i}: error: {e}", file=sys.stderr)
            continue
        if spr['width'] > 0 and spr['height'] > 0:
            decoded.append((i, spr))

    png_name = f'{basename}.png'
    json_path = os.path.join(outdir, f'{basename}.json')

    if not decoded:
        # Nothing to pack: emit a 1x1 transparent sheet + empty atlas.
        atlas = {"file": png_name, "palette_colors": len(palette), "sprites": []}
        with open(os.path.join(outdir, png_name), 'wb') as f:
            f.write(encode_png_rgba(1, 1, b'\x00\x00\x00\x00'))
        with open(json_path, 'w') as f:
            json.dump(atlas, f, indent=2)
        return atlas

    # Choose a sheet width: aim for a roughly square sheet by total area.
    total_area = sum(s['width'] * s['height'] for _, s in decoded)
    widest = max(s['width'] for _, s in decoded)
    import math
    target = max(widest, int(math.sqrt(total_area) * 1.3) + 1)

    boxes = [(i, s['width'], s['height']) for i, s in decoded]
    placements, sheet_w, sheet_h = _shelf_pack(boxes, target)

    if sheet_w == 0 or sheet_h == 0:
        sheet_w = max(1, widest)
        sheet_h = max(1, max(s['height'] for _, s in decoded))

    # Compose the sheet (RGBA, transparent background).
    sheet = bytearray(sheet_w * sheet_h * 4)
    by_index = {i: s for i, s in decoded}
    sprites_meta = []
    for idx, x, y, w, h in placements:
        spr = by_index[idx]
        rgba = sprite_to_rgba(spr, palette, opaque=opaque)
        for row in range(h):
            dst = ((y + row) * sheet_w + x) * 4
            src = row * w * 4
            sheet[dst:dst + w * 4] = rgba[src:src + w * 4]
        sprites_meta.append({
            "index": idx,
            "x": x, "y": y, "w": w, "h": h,
            "palette_offset": spr['palette_offset'],
        })

    sprites_meta.sort(key=lambda m: m["index"])
    atlas = {
        "file": png_name,
        "palette_colors": len(palette),
        "sprites": sprites_meta,
    }

    with open(os.path.join(outdir, png_name), 'wb') as f:
        f.write(encode_png_rgba(sheet_w, sheet_h, bytes(sheet)))
    with open(json_path, 'w') as f:
        json.dump(atlas, f, indent=2)

    return atlas


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
    parser.add_argument('--png', metavar='DIR',
                        help='Export each sprite as a separate RGBA PNG '
                             '(palette index 0 = transparent)')
    parser.add_argument('--atlas', metavar='DIR',
                        help='Pack all non-empty sprites into one PNG sheet '
                             'plus a sibling <basename>.json atlas')
    parser.add_argument('--opaque', action='store_true',
                        help='Make PNG/atlas output fully opaque '
                             '(do not treat palette index 0 as transparent)')
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

    if args.png:
        exported = export_pngs(data, n_sprites, palette, args.png, basename,
                               opaque=args.opaque)
        print(f"Exported {exported}/{n_sprites} sprite PNGs to {args.png}/")
        return 0

    if args.atlas:
        atlas = export_atlas(data, n_sprites, palette, args.atlas, basename,
                             opaque=args.opaque)
        print(f"Packed {len(atlas['sprites'])}/{n_sprites} sprites into "
              f"{args.atlas}/{basename}.png + {basename}.json")
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
