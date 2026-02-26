#!/usr/bin/env python
"""
Dune 1992 COMMAND*.HSQ String Table Decoder

Decodes UI text string tables from COMMAND*.HSQ files.

Format:
  - Offset table: N × uint16 LE (N = first_offset / 2)
  - String data: 0xFF-terminated ASCII strings

Content includes location names, job descriptions, status messages,
and UI format templates. COMMAND1-7 are language variants:
  1=English, 2=French, 3=German, 4=English(?), 5=Spanish, 6=Italian, 7=???

String categories (by index range):
  0-22:   Location/sietch names (Arrakeen, Carthag, Tabr, etc.)
  23-46:  Job/activity descriptions (Spice Mining, Military Training, etc.)
  47-60+: Status messages and format templates
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress


def decode_strings(data):
    """Decode string table from decompressed COMMAND data."""
    if len(data) < 4:
        return []

    first = struct.unpack_from('<H', data, 0)[0]
    n_entries = first // 2
    offsets = [struct.unpack_from('<H', data, i * 2)[0] for i in range(n_entries)]

    strings = []
    for i, off in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < n_entries else len(data)
        chunk = data[off:end]
        term = chunk.find(0xFF)
        if term >= 0:
            text = chunk[:term].decode('ascii', errors='replace')
        else:
            text = chunk.decode('ascii', errors='replace')
        strings.append(text)

    return strings


def main():
    parser = argparse.ArgumentParser(
        description='Dune 1992 COMMAND String Table Decoder')
    parser.add_argument('file', help='COMMAND*.HSQ file')
    parser.add_argument('--raw', action='store_true',
                        help='Input is already decompressed')
    parser.add_argument('--index', type=int, metavar='N',
                        help='Show single string by index')
    parser.add_argument('--search', type=str, metavar='TEXT',
                        help='Search for strings containing TEXT')
    parser.add_argument('--stats', action='store_true',
                        help='Show statistics')
    args = parser.parse_args()

    raw = open(args.file, 'rb').read()
    data = raw if args.raw else hsq_decompress(raw)
    strings = decode_strings(data)

    basename = os.path.splitext(os.path.basename(args.file))[0]

    if args.stats:
        print(f"File: {args.file}")
        print(f"  Compressed:   {len(raw)} bytes")
        print(f"  Decompressed: {len(data)} bytes")
        print(f"  String count: {len(strings)}")
        non_empty = sum(1 for s in strings if s.strip())
        print(f"  Non-empty:    {non_empty}")
        return 0

    if args.index is not None:
        if args.index >= len(strings):
            print(f"Error: index {args.index} out of range (0-{len(strings)-1})",
                  file=sys.stderr)
            return 1
        print(f"[{args.index}] {strings[args.index]}")
        return 0

    if args.search:
        needle = args.search.lower()
        for i, s in enumerate(strings):
            if needle in s.lower():
                print(f"  [{i:3d}] {s}")
        return 0

    # Default: show all non-empty strings
    print(f"{basename}: {len(strings)} strings")
    for i, s in enumerate(strings):
        if s.strip():
            print(f"  [{i:3d}] {s}")

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
