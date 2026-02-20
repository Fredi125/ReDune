#!/usr/bin/env python3
"""
Dune 1992 DUNE.DAT Archive Decoder

Reads and extracts files from the DUNE.DAT archive (Cryo Interactive, CD version).

DUNE.DAT format:
  Header (64KB = 0x10000):
    - uint16 LE: file count (0x0A3D = 2621 for CD v3.7, also version magic)
    - Entry records (25 bytes each):
        - 16 bytes: filename (null-padded, may include subdirectory paths)
        - int32 LE: file size
        - int32 LE: file offset (absolute, from start of archive)
        - 1 byte:   flag (unused in CD version)
    - Entries terminated by name[0] == 0x00
    - Remaining header bytes zero-padded to 0x10000

  Data (starts at 0x10000):
    - File data at offsets specified in header entries
    - HSQ-compressed files auto-detected by checksum (sum of header bytes == 0xAB)

Reference: OpenRakis DuneExtractor.cs, ScummVM archive.cpp

Usage:
  python3 dat_decoder.py DUNE.DAT                   # List all files
  python3 dat_decoder.py DUNE.DAT --stats            # Summary statistics
  python3 dat_decoder.py DUNE.DAT --extract outdir/  # Extract all files
  python3 dat_decoder.py DUNE.DAT --find "*.HNM"     # Find files by pattern
  python3 dat_decoder.py DUNE.DAT --info CONDIT.HSQ   # Show info for one file
"""

import argparse
import fnmatch
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress, hsq_get_sizes

# Version/magic bytes for CD version: uint16 LE 0x0A3D = 2621
DAT_MAGIC = b'\x3D\x0A'

HEADER_SIZE = 0x10000  # 64KB header area
ENTRY_SIZE = 25        # 16 + 4 + 4 + 1


def parse_dat_header(data: bytes) -> list:
    """
    Parse DUNE.DAT header and return list of file entries.

    Each entry: {'name': str, 'size': int, 'offset': int, 'flag': int}

    Args:
        data: At least the first 0x10000 bytes of DUNE.DAT

    Returns:
        List of file entry dicts

    Raises:
        ValueError: If file is too small or has wrong magic
    """
    if len(data) < HEADER_SIZE:
        raise ValueError(f"File too small for DUNE.DAT header: {len(data)} bytes (need {HEADER_SIZE})")

    # Read file count / version magic
    count_hint = struct.unpack_from('<H', data, 0)[0]

    entries = []
    pos = 2  # after count

    while pos + ENTRY_SIZE <= HEADER_SIZE:
        # Read 16-byte filename
        name_bytes = data[pos:pos + 16]
        if name_bytes[0] == 0:
            break  # end of entries

        # Extract null-terminated name
        null_idx = name_bytes.find(b'\x00')
        if null_idx >= 0:
            name = name_bytes[:null_idx].decode('ascii', errors='replace')
        else:
            name = name_bytes.decode('ascii', errors='replace')

        # Read size, offset, flag
        size = struct.unpack_from('<i', data, pos + 16)[0]
        offset = struct.unpack_from('<i', data, pos + 20)[0]
        flag = data[pos + 24]

        entries.append({
            'name': name,
            'size': size,
            'offset': offset,
            'flag': flag,
        })

        pos += ENTRY_SIZE

    return entries


def is_hsq_compressed(data: bytes) -> bool:
    """Check if file data appears to be HSQ-compressed (checksum == 0xAB)."""
    if len(data) < 6:
        return False
    checksum = (data[0] + data[1] + data[2] + data[3] + data[4] + data[5]) & 0xFF
    return checksum == 0xAB


def get_file_ext(name: str) -> str:
    """Get uppercase file extension."""
    _, ext = os.path.splitext(name)
    return ext.upper()


def classify_file(name: str) -> str:
    """Classify a file by extension/name into a category."""
    ext = get_file_ext(name)
    upper = name.upper()

    if ext == '.HNM':
        return 'video'
    elif ext == '.VOC':
        return 'sound'
    elif ext == '.SAL':
        return 'scene'
    elif ext == '.LOP':
        return 'animation'
    elif ext == '.BIN':
        return 'data'
    elif ext == '.HSQ':
        if upper.startswith('COMMAND'):
            return 'script'
        elif upper.startswith(('DNADL', 'DNADP', 'DNADG', 'DNMID', 'DNSDB', 'DNSBP')):
            return 'music'
        elif upper.startswith('SN') or upper == 'FREQ.HSQ':
            return 'sound'
        elif upper.startswith(('IRUL', 'INTDS', 'SUNRS', 'FLY', 'BACK', 'PALAIS')):
            return 'graphics'
        elif upper in ('DIALOGUE.HSQ', 'CONDIT.HSQ', 'PHRASE11.HSQ',
                        'PHRASE12.HSQ', 'PHRASE21.HSQ', 'PHRASE22.HSQ'):
            return 'dialogue'
        elif upper in ('MAP.HSQ', 'GLOBDATA.HSQ'):
            return 'gamedata'
        elif upper.startswith(('DNVGA', 'DNPCS', 'DN386')):
            return 'driver'
        else:
            return 'resource'
    else:
        return 'other'


def list_files(entries: list, pattern: str = None):
    """Print file listing."""
    filtered = entries
    if pattern:
        filtered = [e for e in entries if fnmatch.fnmatch(e['name'].upper(), pattern.upper())]

    print(f"{'#':>4}  {'Name':<24} {'Size':>10}  {'Offset':>10}  {'Flag':>4}  {'Category':<12}")
    print('-' * 74)

    total_size = 0
    for i, entry in enumerate(filtered):
        cat = classify_file(entry['name'])
        print(f"{i:>4}  {entry['name']:<24} {entry['size']:>10,}  0x{entry['offset']:08X}  {entry['flag']:>4}  {cat:<12}")
        total_size += entry['size']

    print('-' * 74)
    print(f"Total: {len(filtered)} files, {total_size:,} bytes ({total_size / 1024 / 1024:.1f} MB)")


def show_stats(entries: list):
    """Print summary statistics."""
    # Count by category
    categories = {}
    extensions = {}
    total_size = 0
    has_subdirs = 0

    for entry in entries:
        cat = classify_file(entry['name'])
        ext = get_file_ext(entry['name'])

        categories[cat] = categories.get(cat, 0) + 1
        extensions[ext] = extensions.get(ext, 0) + 1
        total_size += entry['size']

        if '\\' in entry['name'] or '/' in entry['name']:
            has_subdirs += 1

    print(f"DUNE.DAT Archive Statistics")
    print(f"  Total files: {len(entries)}")
    print(f"  Total size: {total_size:,} bytes ({total_size / 1024 / 1024:.1f} MB)")
    print(f"  Files in subdirectories: {has_subdirs}")
    print()

    print(f"  {'Category':<16} {'Count':>6}")
    print(f"  {'-' * 24}")
    for cat in sorted(categories, key=lambda c: -categories[c]):
        print(f"  {cat:<16} {categories[cat]:>6}")
    print()

    print(f"  {'Extension':<16} {'Count':>6}")
    print(f"  {'-' * 24}")
    for ext in sorted(extensions, key=lambda e: -extensions[e]):
        label = ext if ext else '(none)'
        print(f"  {label:<16} {extensions[ext]:>6}")

    # Check offset ranges
    offsets = [e['offset'] for e in entries]
    if offsets:
        print(f"\n  Offset range: 0x{min(offsets):08X} - 0x{max(offsets):08X}")
        # Check for gaps or overlaps
        sorted_entries = sorted(entries, key=lambda e: e['offset'])
        gaps = 0
        overlaps = 0
        for i in range(len(sorted_entries) - 1):
            end = sorted_entries[i]['offset'] + sorted_entries[i]['size']
            next_start = sorted_entries[i + 1]['offset']
            if end < next_start:
                gaps += 1
            elif end > next_start:
                overlaps += 1
        print(f"  Gaps between files: {gaps}")
        print(f"  Overlapping files: {overlaps}")


def show_info(entries: list, dat_data: bytes, name: str):
    """Show detailed info for a specific file."""
    matches = [e for e in entries if e['name'].upper() == name.upper()]
    if not matches:
        # Try partial match
        matches = [e for e in entries if name.upper() in e['name'].upper()]

    if not matches:
        print(f"File not found: {name}")
        return

    for entry in matches:
        print(f"File: {entry['name']}")
        print(f"  Size: {entry['size']:,} bytes")
        print(f"  Offset: 0x{entry['offset']:08X}")
        print(f"  Flag: {entry['flag']}")
        print(f"  Category: {classify_file(entry['name'])}")

        # Check if HSQ compressed
        if entry['offset'] + entry['size'] <= len(dat_data):
            file_data = dat_data[entry['offset']:entry['offset'] + entry['size']]
            if is_hsq_compressed(file_data):
                try:
                    decomp, comp, checksum = hsq_get_sizes(file_data)
                    ratio = (1 - entry['size'] / decomp) * 100 if decomp > 0 else 0
                    print(f"  HSQ compressed: yes")
                    print(f"  Decompressed size: {decomp:,} bytes")
                    print(f"  Compression ratio: {ratio:.1f}%")
                except Exception:
                    print(f"  HSQ compressed: yes (header parse error)")
            else:
                print(f"  HSQ compressed: no")

            # Show first bytes
            preview = ' '.join(f'{b:02X}' for b in file_data[:32])
            print(f"  First 32 bytes: {preview}")
        else:
            print(f"  (data beyond available bytes)")
        print()


def extract_files(entries: list, dat_data: bytes, outdir: str, decompress: bool = False):
    """Extract all files from the archive."""
    extracted = 0
    errors = 0

    for entry in entries:
        name = entry['name']
        # Convert backslash paths to forward slash for filesystem
        rel_path = name.replace('\\', os.sep)
        out_path = os.path.join(outdir, rel_path)

        # Create parent directory
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if entry['offset'] + entry['size'] > len(dat_data):
            print(f"  SKIP {name}: data beyond file end", file=sys.stderr)
            errors += 1
            continue

        file_data = dat_data[entry['offset']:entry['offset'] + entry['size']]

        if decompress and is_hsq_compressed(file_data):
            try:
                file_data = hsq_decompress(file_data)
                name_note = f" (decompressed: {len(file_data):,} bytes)"
            except Exception as e:
                name_note = f" (HSQ decompress failed: {e})"
        else:
            name_note = ""

        with open(out_path, 'wb') as f:
            f.write(file_data)
        extracted += 1
        print(f"  {name}{name_note}")

    print(f"\nExtracted {extracted} files to {outdir}/ ({errors} errors)")


def main():
    parser = argparse.ArgumentParser(
        description='Dune 1992 DUNE.DAT Archive Decoder')
    parser.add_argument('datfile', help='Path to DUNE.DAT')
    parser.add_argument('--stats', action='store_true',
                        help='Show summary statistics')
    parser.add_argument('--find', metavar='PATTERN',
                        help='Find files matching pattern (e.g., "*.HNM")')
    parser.add_argument('--info', metavar='NAME',
                        help='Show detailed info for a specific file')
    parser.add_argument('--extract', metavar='OUTDIR',
                        help='Extract all files to directory')
    parser.add_argument('--decompress', action='store_true',
                        help='Decompress HSQ files during extraction')
    parser.add_argument('--header-only', action='store_true',
                        help='Only read header (faster for large files)')
    args = parser.parse_args()

    if not os.path.exists(args.datfile):
        print(f"File not found: {args.datfile}", file=sys.stderr)
        return 1

    # Read file (or just header for listing)
    if args.header_only or (not args.extract and not args.info):
        with open(args.datfile, 'rb') as f:
            data = f.read(HEADER_SIZE)
    else:
        data = open(args.datfile, 'rb').read()

    # Validate magic
    if len(data) >= 2 and data[:2] != DAT_MAGIC:
        count = struct.unpack_from('<H', data, 0)[0]
        print(f"Warning: unexpected count/magic: 0x{data[0]:02X}{data[1]:02X} "
              f"(expected 0x3D0A = 2621, got {count})", file=sys.stderr)

    entries = parse_dat_header(data)
    print(f"DUNE.DAT: {len(entries)} files\n")

    if args.stats:
        show_stats(entries)
    elif args.find:
        list_files(entries, args.find)
    elif args.info:
        if len(data) < HEADER_SIZE:
            print("Need full file for --info, re-reading...", file=sys.stderr)
            data = open(args.datfile, 'rb').read()
        show_info(entries, data, args.info)
    elif args.extract:
        if len(data) <= HEADER_SIZE:
            print("Need full file for --extract, re-reading...", file=sys.stderr)
            data = open(args.datfile, 'rb').read()
        extract_files(entries, data, args.extract, args.decompress)
    else:
        list_files(entries)

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
