#!/usr/bin/env python
"""
Dune 1992 SAL Scene File Encoder
==================================
Inverse of tools/sal_decoder.py — encode a parsed SAL structure back to the
binary .SAL format used for interior room rendering.

SAL files (VILG.SAL, SIET.SAL, PALACE.SAL, HARK.SAL) define the visual layout
of game locations. The on-disk format (see sal_decoder.py for the full spec):

  - Offset table: N × uint16 LE pointers to sections (N = first_offset / 2)
  - Sections laid out back-to-back immediately after the offset table.

  Section:
    - Byte 0: sprite slot count
    - Command stream (uint16 LE words), terminated by 0xFFFF:
        Sprite     (5 bytes): word[flags|x_bit8|index+1], x_lo, y, pal
        Rect fill (10 bytes): 0xC0xx header + x1, y1, x2, y2 (uint16 each)
        Polygon (variable):   AHAL header, x_off/y_off (signed ×16), init x/y,
                              pass-1 verts (bit 14 ends pass 1; bit 15 ends all),
                              pass-2 verts (bit 15 ends)

This encoder rebuilds the offset table from scratch (sections concatenated in
order), so a decode → encode round-trip is byte-identical for all four shipped
SAL files (verified with --test).

Usage:
  python sal_encoder.py --test gamedata/SIET.SAL          # round-trip check
  python sal_encoder.py --test gamedata/*.SAL             # check several
  python sal_encoder.py --from-json scene.json -o OUT.SAL # build from JSON
  python sal_encoder.py gamedata/PALACE.SAL --to-json out.json  # dump JSON

JSON schema (compatible with --from-json; one section per list entry):
  {
    "file": "<source name>",
    "section_count": N,
    "sections": [
      {
        "sprite_slots": <int>,
        "commands": [
          {"type": "sprite", "sprite_index": i, "x": .., "y": .., "flags": ..,
           "palette_offset": ..},
          {"type": "rect_fill", "header": .., "x1": .., "y1": .., "x2": .., "y2": ..},
          {"type": "polygon", "poly_type": .., "poly_subtype": ..,
           "x_offset": .., "y_offset": .., "init_x": .., "init_y": ..,
           "vertices_pass1": [[x, y], ...], "vertices_pass2": [[x, y], ...]},
          {"type": "terminator"}
        ]
      }, ...
    ]
  }
"""

import argparse
import json
import os
import struct
import sys
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

# Reuse the decoder so --test and --to-json stay in lockstep with the parser.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sal_decoder import parse_sal, decode_section


# =============================================================================
# SECTION ENCODER (inverse of sal_decoder.decode_section)
# =============================================================================

def encode_section(section: dict) -> bytes:
    """Encode one parsed SAL section dict back to bytes.

    Mirrors sal_decoder.decode_section exactly. The section dict must provide
    ``sprite_slots`` (int) and ``commands`` (list of command dicts). Vertex
    lists may be tuples or 2-element lists. ``terminator`` commands emit the
    0xFFFF word; if no terminator command is present, one is appended so the
    section is well-formed.

    Raises:
        ValueError: on an unknown command type.
    """
    out = bytearray()
    out.append(section.get('sprite_slots', 0) & 0xFF)

    has_terminator = False
    for cmd in section.get('commands', []):
        ctype = cmd['type']

        if ctype == 'sprite':
            # word: bits[15:10]=flags, bit9=x_bit8, bits[8:0]=sprite_index+1
            sprite_index = (cmd['sprite_index'] + 1) & 0x1FF
            x = cmd['x'] & 0x1FF
            x_bit8 = (x >> 8) & 1
            flags = cmd.get('flags', 0) & 0x3F
            word = (flags << 10) | (x_bit8 << 9) | sprite_index
            out += struct.pack('<H', word)
            out.append(x & 0xFF)
            out.append(cmd['y'] & 0xFF)
            out.append(cmd['palette_offset'] & 0xFF)

        elif ctype == 'rect_fill':
            out += struct.pack('<H', cmd['header'] & 0xFFFF)
            out += struct.pack('<HHHH',
                               cmd['x1'] & 0xFFFF, cmd['y1'] & 0xFFFF,
                               cmd['x2'] & 0xFFFF, cmd['y2'] & 0xFFFF)

        elif ctype == 'polygon':
            word = ((cmd['poly_type'] & 0xFF) << 8) | (cmd['poly_subtype'] & 0xFF)
            out += struct.pack('<H', word)
            # x_offset / y_offset are stored as signed bytes ×16
            x_off = (cmd.get('x_offset', 0) // 16) & 0xFF
            y_off = (cmd.get('y_offset', 0) // 16) & 0xFF
            out.append(x_off)
            out.append(y_off)
            out += struct.pack('<HH', cmd.get('init_x', 0) & 0xFFFF,
                               cmd.get('init_y', 0) & 0xFFFF)

            pass1 = cmd.get('vertices_pass1', [])
            pass2 = cmd.get('vertices_pass2', [])

            for k, vert in enumerate(pass1):
                vx, vy = vert[0], vert[1]
                raw = vx & 0x3FFF
                if k == len(pass1) - 1:
                    raw |= 0x4000  # last vertex of pass 1
                    if not pass2:
                        raw |= 0x8000  # also final vertex overall
                out += struct.pack('<HH', raw, vy & 0xFFFF)

            for k, vert in enumerate(pass2):
                vx, vy = vert[0], vert[1]
                raw = vx & 0x3FFF
                if k == len(pass2) - 1:
                    raw |= 0x8000  # final vertex overall
                out += struct.pack('<HH', raw, vy & 0xFFFF)

        elif ctype == 'terminator':
            out += struct.pack('<H', 0xFFFF)
            has_terminator = True

        elif ctype in ('sprite_truncated', 'rect_fill_truncated'):
            # Truncated markers carry no re-encodable payload; skip.
            pass

        else:
            raise ValueError(f"unknown SAL command type: {ctype!r}")

    if not has_terminator:
        out += struct.pack('<H', 0xFFFF)

    return bytes(out)


def encode_sal(sections: List[dict]) -> bytes:
    """Encode a list of section dicts into a complete .SAL file.

    The offset table is rebuilt: ``len(sections)`` uint16 LE pointers followed
    by every encoded section, concatenated in order.
    """
    encoded = [encode_section(s) for s in sections]

    table_size = len(encoded) * 2
    offsets = []
    pos = table_size
    for blob in encoded:
        offsets.append(pos)
        pos += len(blob)

    out = bytearray()
    for off in offsets:
        out += struct.pack('<H', off & 0xFFFF)
    for blob in encoded:
        out += blob
    return bytes(out)


# =============================================================================
# DECODE → STRUCTURE (for --to-json and --test)
# =============================================================================

def decode_to_sections(data: bytes) -> List[dict]:
    """Decode a SAL file into a list of JSON-serializable section dicts.

    Wraps sal_decoder.decode_section and strips the non-serializable ``raw``
    field while converting vertex tuples to lists.
    """
    count, offsets, _ = parse_sal(data)
    sections = []
    for i in range(count):
        end = offsets[i + 1] if i + 1 < count else len(data)
        sec = decode_section(data, offsets[i], end)
        sections.append(_section_to_jsonable(sec))
    return sections


def _section_to_jsonable(sec: dict) -> dict:
    """Convert a decoded section into a clean, JSON-serializable dict."""
    out_cmds = []
    for cmd in sec['commands']:
        c = {k: v for k, v in cmd.items() if k != 'offset'}
        if cmd['type'] == 'polygon':
            c['vertices_pass1'] = [list(v) for v in cmd.get('vertices_pass1', [])]
            c['vertices_pass2'] = [list(v) for v in cmd.get('vertices_pass2', [])]
        out_cmds.append(c)
    return {'sprite_slots': sec['sprite_slots'], 'commands': out_cmds}


# =============================================================================
# ROUND-TRIP TEST
# =============================================================================

def roundtrip_test(path: str) -> dict:
    """Decode → re-encode a SAL file and check fidelity.

    Asserts the re-encoded bytes decode to the SAME structure, and reports the
    byte-identical match. Returns a result dict.
    """
    with open(path, 'rb') as f:
        original = f.read()

    sections = decode_to_sections(original)
    reencoded = encode_sal(sections)

    # Structural equality: re-encoded must decode to the same section list.
    sections2 = decode_to_sections(reencoded)
    structural_match = (sections == sections2)

    byte_identical = (reencoded == original)

    # Locate first byte difference for diagnostics.
    first_diff = None
    if not byte_identical:
        limit = min(len(original), len(reencoded))
        for i in range(limit):
            if original[i] != reencoded[i]:
                first_diff = i
                break
        if first_diff is None:
            first_diff = limit  # length differs

    return {
        'file': path,
        'original_size': len(original),
        'reencoded_size': len(reencoded),
        'byte_identical': byte_identical,
        'structural_match': structural_match,
        'first_diff': first_diff,
        'section_count': len(sections),
    }


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(
        description='Dune 1992 SAL Scene File Encoder (inverse of sal_decoder)',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('files', nargs='*',
                   help='SAL file(s) for --test / --to-json')
    p.add_argument('--test', action='store_true',
                   help='Round-trip mode: decode, re-encode, assert structural '
                        'equality and report byte-identical match rate')
    p.add_argument('--from-json', metavar='FILE',
                   help='Build a .SAL from a JSON scene description')
    p.add_argument('--to-json', metavar='FILE',
                   help='Decode the input SAL and write its JSON structure '
                        '(use with a single SAL file argument)')
    p.add_argument('-o', '--output', metavar='FILE',
                   help='Output .SAL path (for --from-json)')
    args = p.parse_args()

    # --- Build from JSON ---
    if args.from_json:
        with open(args.from_json) as f:
            doc = json.load(f)
        sections = doc['sections'] if isinstance(doc, dict) else doc
        data = encode_sal(sections)
        if args.output:
            with open(args.output, 'wb') as f:
                f.write(data)
            print(f"Wrote {len(data)} bytes → {args.output} "
                  f"({len(sections)} sections)")
        else:
            sys.stdout.buffer.write(data)
        return 0

    # --- Dump JSON ---
    if args.to_json:
        if len(args.files) != 1:
            print("--to-json requires exactly one SAL file argument",
                  file=sys.stderr)
            return 1
        with open(args.files[0], 'rb') as f:
            data = f.read()
        sections = decode_to_sections(data)
        doc = {
            'file': os.path.basename(args.files[0]),
            'section_count': len(sections),
            'sections': sections,
        }
        with open(args.to_json, 'w') as f:
            json.dump(doc, f, indent=2)
        print(f"Wrote JSON: {args.to_json} ({len(sections)} sections)")
        return 0

    # --- Round-trip test ---
    if args.test:
        if not args.files:
            print("--test requires at least one SAL file", file=sys.stderr)
            return 1
        all_exact = True
        n_exact = 0
        for path in args.files:
            if not os.path.exists(path):
                print(f"File not found: {path}", file=sys.stderr)
                all_exact = False
                continue
            r = roundtrip_test(path)
            assert r['structural_match'], (
                f"{path}: re-encode does NOT decode to the same structure")
            status = "IDENTICAL" if r['byte_identical'] else "DIFF"
            extra = ""
            if not r['byte_identical']:
                extra = (f"  (orig={r['original_size']}b "
                         f"reenc={r['reencoded_size']}b "
                         f"first_diff@{r['first_diff']})")
                all_exact = False
            else:
                n_exact += 1
            print(f"  {os.path.basename(path):14s} {r['section_count']:3d} sections  "
                  f"structural=OK  byte={status}{extra}")
        total = len([f for f in args.files if os.path.exists(f)])
        if total:
            pct = 100.0 * n_exact / total
            print(f"\n  Byte-identical round-trip: {n_exact}/{total} files "
                  f"({pct:.1f}%)")
        return 0 if all_exact else 2

    p.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
