#!/usr/bin/env python
"""
Dune 1992 HSQ Decompressor
============================
Decompress HSQ (Cryo Interactive LZ77-variant) compressed game resources.

Usage:
  python hsq_decompress.py CONDIT.HSQ                    # Decompress to CONDIT.bin
  python hsq_decompress.py CONDIT.HSQ -o CONDIT_dec.bin   # Custom output name
  python hsq_decompress.py CONDIT.HSQ --info              # Show header info only
  python hsq_decompress.py *.HSQ                          # Batch decompress
"""

import sys
import os
import argparse
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.compression import hsq_decompress, hsq_get_sizes


def main():
    p = argparse.ArgumentParser(description='Dune 1992 HSQ Decompressor')
    p.add_argument('files', nargs='+', help='HSQ file(s) to decompress')
    p.add_argument('-o', '--output', default=None, help='Output file (single file mode only)')
    p.add_argument('--info', action='store_true', help='Show header info without decompressing')
    args = p.parse_args()

    # Expand globs on Windows
    files = []
    for pattern in args.files:
        expanded = glob.glob(pattern)
        files.extend(expanded if expanded else [pattern])

    for path in files:
        with open(path, 'rb') as f:
            raw = f.read()

        try:
            decomp_size, comp_size, checksum = hsq_get_sizes(raw)
        except ValueError as e:
            print(f"  SKIP {path}: {e}")
            continue

        if args.info:
            print(f"  {path}: {len(raw)} bytes → {decomp_size} bytes (header says comp={comp_size}, checksum=0x{checksum:04X})")
            continue

        try:
            data = hsq_decompress(raw)
        except ValueError as e:
            print(f"  ERROR {path}: {e}")
            continue

        if args.output and len(files) == 1:
            out_path = args.output
        else:
            base = os.path.splitext(path)[0]
            out_path = base + '.bin'

        with open(out_path, 'wb') as f:
            f.write(data)

        ratio = len(data) / len(raw) if len(raw) > 0 else 0
        print(f"  {path}: {len(raw):,} → {len(data):,} bytes ({ratio:.1f}x) → {out_path}")


if __name__ == '__main__':
    main()
