#!/usr/bin/env python3
"""
Dune 1992 SAL Scene File Decoder
===================================
Decode SAL scene layout files used for interior room rendering.

SAL files (VILG.SAL, SIET.SAL, PALACE.SAL, HARK.SAL) define the visual
layout of game locations (sietches, palace rooms, Harkonnen fortress).

File structure:
  - Offset table: N × uint16 LE pointers to sections
  - Each section contains drawing commands for one room/view

Section format:
  - Byte 0: sprite slot count (consumed by stack buffer init)
  - Command stream: series of uint16 LE words processed sequentially

Command types (determined by the uint16 word read via x86 LODSW):
  0xFFFF              → Terminator (end of section)
  Bit 15 clear        → Sprite draw command (5 bytes total)
  Bit 15 set, AH!=C0  → Polygon command (variable length)
  Bit 15 set, AH==C0  → Rectangle fill (10 bytes total)

Sprite entry encoding (from DNCDPRG.ASM sub_13B59):
  word[15:10] = flags (6 bits)
  word[9]     = X coordinate bit 8 (extends X to 9 bits)
  word[8:0]   = sprite_index + 1 (1-based; dec'd before draw_sprite call)
  byte[2]     = X coordinate low 8 bits
  byte[3]     = Y coordinate (8 bits)
  byte[4]     = palette offset

Polygon entry (from DNCDPRG.ASM sub_13BE9):
  word        = header (AH=poly_type, AL=poly_subtype)
  byte        = X offset (signed, ×16)
  byte        = Y offset (signed, ×16)
  word        = initial X (first point)
  word        = initial Y (first point)
  word pairs  = vertices; bit 14 set on last of pass 1, bit 15 set on final

Rectangle fill entry:
  word        = header (0xC0xx)
  word        = X1
  word        = Y1
  word        = X2
  word        = Y2

Usage:
  python3 sal_decoder.py VILG.SAL              # Decode all sections
  python3 sal_decoder.py PALACE.SAL --section 5  # Single section
  python3 sal_decoder.py SIET.SAL --stats        # Statistics
  python3 sal_decoder.py HARK.SAL --raw          # Include raw hex
"""

import struct
import sys
import argparse
import os
from typing import Optional


# =============================================================================
# SAL PARSER
# =============================================================================

def parse_sal(data: bytes) -> tuple:
    """
    Parse SAL file structure.

    Returns: (section_count, offsets_list, data_bytes)
    """
    if len(data) < 2:
        raise ValueError("SAL file too short")

    first_offset = struct.unpack_from('<H', data, 0)[0]
    section_count = first_offset // 2

    offsets = []
    for i in range(section_count):
        off = struct.unpack_from('<H', data, i * 2)[0]
        offsets.append(off)

    return section_count, offsets, data


def decode_section(data: bytes, offset: int, end: int) -> dict:
    """
    Decode a single SAL section into structured commands.

    Returns dict with:
      sprite_slots: int (first byte)
      commands: list of command dicts
      raw: bytes
    """
    section = data[offset:end]
    if len(section) < 1:
        return {"sprite_slots": 0, "commands": [], "raw": section}

    sprite_slots = section[0]
    commands = []
    pos = 1  # Skip sprite_slots byte

    while pos + 1 < len(section):
        # Read uint16 LE word
        word = struct.unpack_from('<H', section, pos)[0]
        pos += 2

        if word == 0xFFFF:
            commands.append({"type": "terminator", "offset": pos - 2})
            break

        if word & 0x8000:
            # High bit set: polygon or rectangle fill
            ah = (word >> 8) & 0xFF
            al = word & 0xFF

            if ah == 0xC0:
                # Rectangle fill: read 4 more words
                if pos + 8 <= len(section):
                    x1 = struct.unpack_from('<H', section, pos)[0]; pos += 2
                    y1 = struct.unpack_from('<H', section, pos)[0]; pos += 2
                    x2 = struct.unpack_from('<H', section, pos)[0]; pos += 2
                    y2 = struct.unpack_from('<H', section, pos)[0]; pos += 2
                    commands.append({
                        "type": "rect_fill",
                        "offset": pos - 10,
                        "header": word,
                        "x1": x1, "y1": y1,
                        "x2": x2, "y2": y2,
                    })
                else:
                    commands.append({"type": "rect_fill_truncated", "offset": pos - 2})
                    break
            else:
                # Polygon: variable length
                cmd = {
                    "type": "polygon",
                    "offset": pos - 2,
                    "poly_type": ah,
                    "poly_subtype": al,
                    "vertices": [],
                }

                if pos + 4 <= len(section):
                    # Read X/Y offsets (signed bytes ×16)
                    x_off = section[pos]; pos += 1
                    y_off = section[pos]; pos += 1
                    if x_off > 127: x_off -= 256
                    if y_off > 127: y_off -= 256
                    cmd["x_offset"] = x_off * 16
                    cmd["y_offset"] = y_off * 16

                    # Read initial point
                    if pos + 4 <= len(section):
                        init_x = struct.unpack_from('<H', section, pos)[0]; pos += 2
                        init_y = struct.unpack_from('<H', section, pos)[0]; pos += 2
                        cmd["init_x"] = init_x
                        cmd["init_y"] = init_y

                        # Read pass 1 vertices (until bit 14 set)
                        pass1 = []
                        while pos + 4 <= len(section):
                            vx_raw = struct.unpack_from('<H', section, pos)[0]; pos += 2
                            vy = struct.unpack_from('<H', section, pos)[0]; pos += 2
                            vx = vx_raw & 0x3FFF
                            pass1.append((vx, vy))
                            if vx_raw & 0x4000:
                                break

                        # Read pass 2 vertices (until bit 15 set)
                        pass2 = []
                        if not (vx_raw & 0x8000):
                            while pos + 4 <= len(section):
                                vx_raw = struct.unpack_from('<H', section, pos)[0]; pos += 2
                                vy = struct.unpack_from('<H', section, pos)[0]; pos += 2
                                vx = vx_raw & 0x3FFF
                                pass2.append((vx, vy))
                                if vx_raw & 0x8000:
                                    break

                        cmd["vertices_pass1"] = pass1
                        cmd["vertices_pass2"] = pass2

                commands.append(cmd)
        else:
            # Sprite draw command
            sprite_index = (word & 0x1FF) - 1  # 1-based → 0-based
            x_bit8 = (word >> 9) & 1
            flags = (word >> 10) & 0x3F

            if pos + 3 <= len(section):
                x_lo = section[pos]; pos += 1
                y = section[pos]; pos += 1
                pal = section[pos]; pos += 1

                x = (x_bit8 << 8) | x_lo

                commands.append({
                    "type": "sprite",
                    "offset": pos - 5,
                    "sprite_index": sprite_index,
                    "x": x, "y": y,
                    "palette_offset": pal,
                    "flags": flags,
                })
            else:
                commands.append({"type": "sprite_truncated", "offset": pos - 2})
                break

    return {
        "sprite_slots": sprite_slots,
        "commands": commands,
        "raw": section,
    }


# =============================================================================
# DISPLAY
# =============================================================================

def show_section(section_data: dict, section_idx: int, show_raw: bool = False):
    """Display a decoded SAL section."""
    cmds = section_data["commands"]
    sprites = [c for c in cmds if c["type"] == "sprite"]
    polys = [c for c in cmds if c["type"] == "polygon"]
    rects = [c for c in cmds if c["type"] == "rect_fill"]

    print(f"  Section [{section_idx}] — "
          f"slots={section_data['sprite_slots']} "
          f"sprites={len(sprites)} polys={len(polys)} rects={len(rects)} "
          f"({len(section_data['raw'])} bytes)")

    for cmd in cmds:
        if cmd["type"] == "sprite":
            flag_str = f" flags=0x{cmd['flags']:02X}" if cmd['flags'] else ""
            pal_str = f" pal=0x{cmd['palette_offset']:02X}" if cmd['palette_offset'] else ""
            print(f"    SPRITE idx={cmd['sprite_index']:3d} "
                  f"pos=({cmd['x']:3d},{cmd['y']:3d})"
                  f"{flag_str}{pal_str}")

        elif cmd["type"] == "polygon":
            n_verts = len(cmd.get("vertices_pass1", [])) + len(cmd.get("vertices_pass2", []))
            print(f"    POLY   type=0x{cmd['poly_type']:02X} sub=0x{cmd['poly_subtype']:02X} "
                  f"offset=({cmd.get('x_offset', 0)},{cmd.get('y_offset', 0)}) "
                  f"init=({cmd.get('init_x', 0)},{cmd.get('init_y', 0)}) "
                  f"verts={n_verts}")

        elif cmd["type"] == "rect_fill":
            print(f"    RECT   ({cmd['x1']},{cmd['y1']})→({cmd['x2']},{cmd['y2']})")

        elif cmd["type"] == "terminator":
            pass  # Don't print terminator

    if show_raw:
        raw_hex = ' '.join(f'{b:02X}' for b in section_data["raw"][:80])
        if len(section_data["raw"]) > 80:
            raw_hex += "..."
        print(f"    RAW: {raw_hex}")

    print()


def show_stats(data: bytes, count: int, offsets: list, filename: str):
    """Show SAL file statistics."""
    print(f"=== SAL Statistics ===")
    print(f"  File:     {os.path.basename(filename)}")
    print(f"  Size:     {len(data):,} bytes")
    print(f"  Sections: {count}")
    print()

    total_sprites = 0
    total_polys = 0
    total_rects = 0

    for i in range(count):
        end = offsets[i + 1] if i + 1 < count else len(data)
        section = decode_section(data, offsets[i], end)
        sprites = len([c for c in section["commands"] if c["type"] == "sprite"])
        polys = len([c for c in section["commands"] if c["type"] == "polygon"])
        rects = len([c for c in section["commands"] if c["type"] == "rect_fill"])
        total_sprites += sprites
        total_polys += polys
        total_rects += rects
        size = end - offsets[i]
        print(f"  [{i:2d}] @0x{offsets[i]:04X} {size:4d}B  "
              f"slots={section['sprite_slots']:2d} "
              f"sprites={sprites:2d} polys={polys:2d} rects={rects}")

    print(f"\n  Totals: {total_sprites} sprites, "
          f"{total_polys} polygons, {total_rects} rect fills")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 SAL Scene File Decoder',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file', help='SAL scene file (e.g. PALACE.SAL)')
    p.add_argument('--section', type=int, default=None, metavar='N',
                   help='Show single section by index')
    p.add_argument('--stats', action='store_true',
                   help='Show statistics')
    p.add_argument('--raw', action='store_true',
                   help='Include raw hex dump')
    args = p.parse_args()

    with open(args.file, 'rb') as f:
        data = f.read()

    count, offsets, data = parse_sal(data)
    print(f"  Loaded: {os.path.basename(args.file)} — "
          f"{len(data):,} bytes, {count} sections\n")

    if args.stats:
        show_stats(data, count, offsets, args.file)
        return

    if args.section is not None:
        if 0 <= args.section < count:
            end = offsets[args.section + 1] if args.section + 1 < count else len(data)
            section = decode_section(data, offsets[args.section], end)
            show_section(section, args.section, args.raw)
        else:
            print(f"Section {args.section} out of range (0-{count - 1})")
        return

    # Default: show all sections
    for i in range(count):
        end = offsets[i + 1] if i + 1 < count else len(data)
        section = decode_section(data, offsets[i], end)
        show_section(section, i, args.raw)


if __name__ == '__main__':
    main()
