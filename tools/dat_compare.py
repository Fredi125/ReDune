#!/usr/bin/env python
"""
DUNE.DAT Roundtrip Comparison Tool

Compares an original DUNE.DAT with a repacked version to identify exactly
what differs and why. Produces a detailed report of:
  - Header magic/count differences
  - Entry ordering differences
  - Filename encoding differences (case, padding)
  - Flag field differences
  - Data offset differences (contiguous vs gaps)
  - File content differences (byte-for-byte)

Usage:
  python dat_compare.py ORIGINAL.DAT REPACKED.DAT
  python dat_compare.py ORIGINAL.DAT REPACKED.DAT --verbose
  python dat_compare.py ORIGINAL.DAT --dump-header          # Dump raw header entries
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

HEADER_SIZE = 0x10000
ENTRY_SIZE = 25


def parse_raw_entries(data: bytes) -> list:
    """Parse header entries preserving raw name bytes and all fields."""
    entries = []
    pos = 2
    while pos + ENTRY_SIZE <= HEADER_SIZE:
        name_bytes = data[pos:pos + 16]
        if name_bytes[0] == 0:
            break
        size = struct.unpack_from('<i', data, pos + 16)[0]
        offset = struct.unpack_from('<i', data, pos + 20)[0]
        flag = data[pos + 24]

        null_idx = name_bytes.find(b'\x00')
        if null_idx >= 0:
            name = name_bytes[:null_idx].decode('ascii', errors='replace')
        else:
            name = name_bytes.decode('ascii', errors='replace')

        entries.append({
            'name': name,
            'name_bytes': bytes(name_bytes),
            'size': size,
            'offset': offset,
            'flag': flag,
            'header_pos': pos,
        })
        pos += ENTRY_SIZE
    return entries


def dump_header(dat_path: str):
    """Dump raw header entries for inspection."""
    with open(dat_path, 'rb') as f:
        data = f.read(HEADER_SIZE)

    magic = struct.unpack_from('<H', data, 0)[0]
    print(f"File: {dat_path}")
    print(f"Magic/count: 0x{magic:04X} ({magic})")
    print()

    entries = parse_raw_entries(data)

    print(f"{'#':>4}  {'Name':<16} {'Size':>10}  {'Offset':>10}  {'Flg':>3}  {'Name hex'}")
    print('-' * 90)

    for i, e in enumerate(entries):
        name_hex = ' '.join(f'{b:02X}' for b in e['name_bytes'])
        print(f"{i:>4}  {e['name']:<16} {e['size']:>10,}  0x{e['offset']:08X}  {e['flag']:>3}  {name_hex}")

    print(f"\nTotal: {len(entries)} entries")

    # Check for gaps between files
    sorted_by_offset = sorted(entries, key=lambda e: e['offset'])
    print(f"\nData layout analysis:")
    prev_end = HEADER_SIZE
    total_gaps = 0
    for e in sorted_by_offset:
        gap = e['offset'] - prev_end
        if gap != 0:
            print(f"  GAP: {gap:,} bytes before {e['name']} (0x{prev_end:08X} -> 0x{e['offset']:08X})")
            total_gaps += abs(gap)
        prev_end = e['offset'] + e['size']
    if total_gaps == 0:
        print(f"  All files contiguous (no gaps)")
    print(f"  Data range: 0x{HEADER_SIZE:08X} -> 0x{prev_end:08X} ({prev_end - HEADER_SIZE:,} bytes)")

    # Check for non-zero flags
    flagged = [e for e in entries if e['flag'] != 0]
    if flagged:
        print(f"\nEntries with non-zero flags ({len(flagged)}):")
        for e in flagged:
            print(f"  {e['name']}: flag={e['flag']}")
    else:
        print(f"\nAll flags are 0x00")

    # Check header padding
    last_entry_end = 2 + len(entries) * ENTRY_SIZE + 1  # +1 for terminator byte
    padding = data[last_entry_end:HEADER_SIZE]
    non_zero_padding = sum(1 for b in padding if b != 0)
    print(f"\nHeader padding: {HEADER_SIZE - last_entry_end:,} bytes after entries")
    if non_zero_padding:
        print(f"  WARNING: {non_zero_padding} non-zero bytes in padding!")
        # Show first few non-zero positions
        count = 0
        for i, b in enumerate(padding):
            if b != 0 and count < 10:
                print(f"    0x{last_entry_end + i:04X}: 0x{b:02X}")
                count += 1
    else:
        print(f"  All padding bytes are 0x00")


def compare_dats(orig_path: str, repack_path: str, verbose: bool = False):
    """Compare two DUNE.DAT files and report all differences."""
    orig_data = open(orig_path, 'rb').read()
    repack_data = open(repack_path, 'rb').read()

    print(f"Original: {orig_path} ({len(orig_data):,} bytes)")
    print(f"Repacked: {repack_path} ({len(repack_data):,} bytes)")
    print()

    issues = 0

    # --- 1. File size ---
    if len(orig_data) != len(repack_data):
        print(f"[DIFF] File size: {len(orig_data):,} vs {len(repack_data):,} "
              f"(delta: {len(repack_data) - len(orig_data):+,})")
        issues += 1
    else:
        print(f"[OK] File sizes match: {len(orig_data):,} bytes")

    # --- 2. Magic/count ---
    orig_magic = struct.unpack_from('<H', orig_data, 0)[0]
    repack_magic = struct.unpack_from('<H', repack_data, 0)[0]
    if orig_magic != repack_magic:
        print(f"[DIFF] Magic/count: 0x{orig_magic:04X} vs 0x{repack_magic:04X}")
        issues += 1
    else:
        print(f"[OK] Magic/count: 0x{orig_magic:04X}")

    # --- 3. Parse entries ---
    orig_entries = parse_raw_entries(orig_data)
    repack_entries = parse_raw_entries(repack_data)

    if len(orig_entries) != len(repack_entries):
        print(f"[DIFF] Entry count: {len(orig_entries)} vs {len(repack_entries)}")
        issues += 1

        # Show which files are extra/missing
        orig_names = set(e['name'] for e in orig_entries)
        repack_names = set(e['name'] for e in repack_entries)
        missing = orig_names - repack_names
        extra = repack_names - orig_names
        if missing:
            print(f"  Missing from repack: {', '.join(sorted(missing))}")
        if extra:
            print(f"  Extra in repack: {', '.join(sorted(extra))}")
    else:
        print(f"[OK] Entry count: {len(orig_entries)}")

    # --- 4. Compare entries by index ---
    n = min(len(orig_entries), len(repack_entries))

    order_diffs = 0
    name_byte_diffs = 0
    size_diffs = 0
    offset_diffs = 0
    flag_diffs = 0
    data_diffs = 0

    for i in range(n):
        oe = orig_entries[i]
        re = repack_entries[i]

        # Name (string comparison)
        if oe['name'] != re['name']:
            order_diffs += 1
            if verbose:
                print(f"  [DIFF] Entry {i}: name '{oe['name']}' vs '{re['name']}'")

        # Name bytes (raw comparison - catches case/padding diffs)
        if oe['name_bytes'] != re['name_bytes']:
            name_byte_diffs += 1
            if verbose:
                orig_hex = ' '.join(f'{b:02X}' for b in oe['name_bytes'])
                repack_hex = ' '.join(f'{b:02X}' for b in re['name_bytes'])
                print(f"  [DIFF] Entry {i} ({oe['name']}): name bytes differ")
                print(f"    orig:   {orig_hex}")
                print(f"    repack: {repack_hex}")

        # Size
        if oe['size'] != re['size']:
            size_diffs += 1
            if verbose:
                print(f"  [DIFF] Entry {i} ({oe['name']}): size {oe['size']:,} vs {re['size']:,}")

        # Offset
        if oe['offset'] != re['offset']:
            offset_diffs += 1
            if verbose:
                print(f"  [DIFF] Entry {i} ({oe['name']}): offset 0x{oe['offset']:08X} vs 0x{re['offset']:08X}")

        # Flag
        if oe['flag'] != re['flag']:
            flag_diffs += 1
            if verbose:
                print(f"  [DIFF] Entry {i} ({oe['name']}): flag {oe['flag']} vs {re['flag']}")

        # Data content
        if oe['offset'] + oe['size'] <= len(orig_data) and re['offset'] + re['size'] <= len(repack_data):
            orig_file_data = orig_data[oe['offset']:oe['offset'] + oe['size']]
            repack_file_data = repack_data[re['offset']:re['offset'] + re['size']]
            if orig_file_data != repack_file_data:
                data_diffs += 1
                if verbose:
                    # Find first differing byte
                    for j in range(min(len(orig_file_data), len(repack_file_data))):
                        if orig_file_data[j] != repack_file_data[j]:
                            print(f"  [DIFF] Entry {i} ({oe['name']}): data differs at byte {j} "
                                  f"(0x{orig_file_data[j]:02X} vs 0x{repack_file_data[j]:02X})")
                            break
                    else:
                        print(f"  [DIFF] Entry {i} ({oe['name']}): data length differs "
                              f"({len(orig_file_data)} vs {len(repack_file_data)})")

    # Summary
    print()
    print("Entry-level comparison summary:")
    for label, count in [
        ("Name order", order_diffs),
        ("Name bytes (raw)", name_byte_diffs),
        ("Size", size_diffs),
        ("Offset", offset_diffs),
        ("Flag", flag_diffs),
        ("Data content", data_diffs),
    ]:
        status = "[DIFF]" if count else "[OK]"
        print(f"  {status} {label}: {count} differences")
        if count:
            issues += 1

    # --- 5. Header padding comparison ---
    orig_pad_start = 2 + len(orig_entries) * ENTRY_SIZE + 1
    repack_pad_start = 2 + len(repack_entries) * ENTRY_SIZE + 1
    orig_padding = orig_data[orig_pad_start:HEADER_SIZE]
    repack_padding = repack_data[repack_pad_start:HEADER_SIZE]
    if orig_padding != repack_padding:
        # Count differing bytes
        pad_diffs = sum(1 for a, b in zip(orig_padding, repack_padding) if a != b)
        pad_diffs += abs(len(orig_padding) - len(repack_padding))
        print(f"\n  [DIFF] Header padding: {pad_diffs} bytes differ")
        issues += 1
    else:
        print(f"\n  [OK] Header padding matches")

    # --- 6. Quick byte-level summary ---
    min_len = min(len(orig_data), len(repack_data))
    byte_diffs = sum(1 for i in range(min_len) if orig_data[i] != repack_data[i])
    byte_diffs += abs(len(orig_data) - len(repack_data))

    print(f"\nOverall: {byte_diffs:,} bytes differ out of {max(len(orig_data), len(repack_data)):,}")

    # Find first difference
    for i in range(min_len):
        if orig_data[i] != repack_data[i]:
            region = "header" if i < HEADER_SIZE else f"data (file offset 0x{i:08X})"
            print(f"First difference at byte {i} (0x{i:08X}) [{region}]: "
                  f"0x{orig_data[i]:02X} vs 0x{repack_data[i]:02X}")
            break

    if issues == 0:
        print("\nFiles are byte-identical!")
    else:
        print(f"\n{issues} categories of differences found.")

    return issues


def main():
    parser = argparse.ArgumentParser(description='DUNE.DAT Roundtrip Comparison Tool')
    parser.add_argument('original', help='Original DUNE.DAT')
    parser.add_argument('repacked', nargs='?', help='Repacked DUNE.DAT (omit for --dump-header)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show per-entry differences')
    parser.add_argument('--dump-header', action='store_true',
                        help='Dump raw header entries for one file')
    args = parser.parse_args()

    if args.dump_header:
        dump_header(args.original)
        return 0

    if not args.repacked:
        parser.error("Need two files to compare (or use --dump-header with one)")

    return compare_dats(args.original, args.repacked, args.verbose)


if __name__ == '__main__':
    sys.exit(main() or 0)
