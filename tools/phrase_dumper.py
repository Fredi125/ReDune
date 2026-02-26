#!/usr/bin/env python
"""
Dune 1992 PHRASE Text Extractor
=================================
Extract dialogue text strings from PHRASE*.HSQ files.

PHRASE files contain the game's dialogue text, organized as:
  - Offset table: N × uint16 LE pointers into string data
  - String data: null-terminated Latin-1 encoded text

String encoding:
  - Standard Latin-1 text (Western European characters)
  - 0xFF (ÿ) bytes are inline separators (alternative text / line breaks)
  - 0x00 null terminates each string

File naming convention:
  PHRASExy.HSQ where:
    x = language (1=EN, 2=FR, 3=DE, 4=ES, 5=IT, 6=??, 7=??)
    y = phrase bank (1=bank 0, 2=bank 1)

  So PHRASE11.HSQ = English bank 0, PHRASE12.HSQ = English bank 1
  PHRASE21.HSQ = French bank 0, PHRASE22.HSQ = French bank 1, etc.

Usage:
  python phrase_dumper.py PHRASE11.HSQ                     # Dump all strings
  python phrase_dumper.py PHRASE11.HSQ --index 0x35        # Single string
  python phrase_dumper.py PHRASE11.HSQ --range 0x35-0x5E   # Range of strings
  python phrase_dumper.py PHRASE11.HSQ --search "Gurney"   # Search text
  python phrase_dumper.py PHRASE11.HSQ --stats             # Statistics
  python phrase_dumper.py PHRASE11.HSQ --raw               # Already decompressed
"""

import struct
import sys
import argparse
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.compression import hsq_decompress


# =============================================================================
# PHRASE FILE PARSER
# =============================================================================

LANGUAGES = {
    '1': 'English',
    '2': 'French',
    '3': 'German',
    '4': 'Spanish',
    '5': 'Italian',
    '6': 'Language6',
    '7': 'Language7',
}


def load_phrase(path: str, is_raw: bool = False) -> tuple:
    """
    Load PHRASE data from HSQ or raw binary file.

    Returns: (data_bytes, string_count, offsets_list)
    """
    with open(path, 'rb') as f:
        raw = f.read()

    if not is_raw:
        try:
            data = hsq_decompress(raw)
        except Exception:
            print("  HSQ decompression failed, treating as raw binary")
            data = raw
    else:
        data = raw

    if len(data) < 2:
        raise ValueError("PHRASE file too short")

    # Parse offset table
    first_offset = struct.unpack_from('<H', data, 0)[0]
    string_count = first_offset // 2

    offsets = []
    for i in range(string_count):
        if i * 2 + 1 >= len(data):
            break
        offsets.append(struct.unpack_from('<H', data, i * 2)[0])

    return bytes(data), string_count, offsets


def get_string_between(data: bytes, start: int, end: int) -> str:
    """
    Extract a string between two offsets.

    PHRASE strings are delimited by the offset table (not null-terminated).
    Each string typically ends with a trailing 0xFF separator byte.
    0xFF bytes within the string separate alternative dialogue variants.

    Returns the string with trailing 0xFF stripped and inline 0xFF shown as '|'.
    """
    if start >= len(data):
        return "<OUT OF RANGE>"

    raw_bytes = data[start:min(end, len(data))]

    # Strip trailing 0xFF separator
    while raw_bytes and raw_bytes[-1] == 0xFF:
        raw_bytes = raw_bytes[:-1]

    text = ''
    for b in raw_bytes:
        if b == 0xFF:
            text += ' | '
        elif b >= 0x20:
            text += chr(b)
        else:
            text += f'\\x{b:02X}'
    return text


def get_raw_between(data: bytes, start: int, end: int) -> bytes:
    """Extract raw bytes of a string between offsets."""
    if start >= len(data):
        return b''
    return data[start:min(end, len(data))]


# =============================================================================
# DISPLAY MODES
# =============================================================================

def detect_language(filename: str) -> str:
    """Try to detect language from PHRASE filename."""
    base = os.path.basename(filename).upper()
    if base.startswith('PHRASE') and len(base) >= 8:
        lang_code = base[6]
        bank_code = base[7]
        lang = LANGUAGES.get(lang_code, f'Language{lang_code}')
        bank = f'bank {int(bank_code) - 1}' if bank_code.isdigit() else f'file {bank_code}'
        return f"{lang} {bank}"
    return "unknown"


def string_end(offsets: list, idx: int, data_len: int) -> int:
    """Get the end offset for string at index idx."""
    return offsets[idx + 1] if idx + 1 < len(offsets) else data_len


def show_all(data: bytes, offsets: list, filename: str):
    """Dump all strings."""
    lang_info = detect_language(filename)
    print(f"  Language: {lang_info}")
    print(f"  Strings: {len(offsets)}\n")

    for i in range(len(offsets)):
        end = string_end(offsets, i, len(data))
        text = get_string_between(data, offsets[i], end)
        print(f"[{i:3d}] (0x{i:03X}) {text}")


def show_index(data: bytes, offsets: list, idx: int):
    """Show a single string by index."""
    if idx < 0 or idx >= len(offsets):
        print(f"Index {idx} out of range (0-{len(offsets) - 1})")
        return

    start = offsets[idx]
    end = string_end(offsets, idx, len(data))
    text = get_string_between(data, start, end)
    raw = get_raw_between(data, start, end)

    print(f"String [{idx}] (0x{idx:03X}) @ offset 0x{start:04X}:")
    print(f"  Length: {len(raw)} bytes")
    print(f"  Text:   {text}")

    # Show 0xFF split parts if the text contains separators
    sep_marker = b'\xFF'
    parts = raw.split(sep_marker)
    # Filter out empty trailing parts
    parts = [p for p in parts if p]
    if len(parts) > 1:
        print(f"  Parts ({len(parts)}):")
        for j, part in enumerate(parts):
            print(f"    [{j}] {part.decode('latin-1', errors='replace')}")


def show_range(data: bytes, offsets: list, range_str: str):
    """Show a range of strings (e.g. '0x35-0x5E')."""
    parts = range_str.split('-')
    start_idx = int(parts[0], 0)
    end_idx = int(parts[1], 0) if len(parts) > 1 else start_idx

    for i in range(start_idx, min(end_idx + 1, len(offsets))):
        end = string_end(offsets, i, len(data))
        text = get_string_between(data, offsets[i], end)
        print(f"[{i:3d}] (0x{i:03X}) {text}")


def show_search(data: bytes, offsets: list, query: str):
    """Search for strings containing the query text."""
    query_lower = query.lower()
    matches = 0

    for i in range(len(offsets)):
        end = string_end(offsets, i, len(data))
        text = get_string_between(data, offsets[i], end)
        if query_lower in text.lower():
            print(f"[{i:3d}] (0x{i:03X}) {text}")
            matches += 1

    print(f"\n  Found {matches} matches for '{query}'")


def show_stats(data: bytes, offsets: list, filename: str):
    """Show PHRASE file statistics."""
    lang_info = detect_language(filename)

    total_len = 0
    sep_count = 0
    lengths = []
    sep_marker = b'\xFF'

    for i in range(len(offsets)):
        end = string_end(offsets, i, len(data))
        raw = get_raw_between(data, offsets[i], end)
        total_len += len(raw)
        lengths.append(len(raw))
        sep_count += raw.count(sep_marker)

    strings_with_sep = sum(
        1 for i in range(len(offsets))
        if sep_marker in get_raw_between(data, offsets[i], string_end(offsets, i, len(data)))
    )

    print(f"=== PHRASE Statistics ===")
    print(f"  File:             {os.path.basename(filename)}")
    print(f"  Language:         {lang_info}")
    print(f"  Data size:        {len(data):,} bytes")
    print(f"  String count:     {len(offsets)}")
    print(f"  Total text bytes: {total_len:,}")
    print(f"  Avg string len:   {total_len / len(offsets):.1f}" if offsets else "")
    print(f"  Min string len:   {min(lengths)}" if lengths else "")
    print(f"  Max string len:   {max(lengths)}" if lengths else "")
    print(f"  Separator (0xFF): {sep_count} occurrences in {strings_with_sep} strings")
    print(f"  Offset table:     0x0000-0x{offsets[0] - 1:04X} ({offsets[0]} bytes)")
    print(f"  String data:      0x{offsets[0]:04X}-0x{len(data):04X} ({len(data) - offsets[0]:,} bytes)")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 PHRASE Text Extractor',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file', help='PHRASE*.HSQ or decompressed binary')
    p.add_argument('--raw', action='store_true',
                   help='Input is already decompressed')
    p.add_argument('--index', type=str, default=None, metavar='N',
                   help='Show single string (decimal or 0x hex)')
    p.add_argument('--range', type=str, default=None, metavar='A-B',
                   help='Show range of strings (e.g. 0x35-0x5E)')
    p.add_argument('--search', type=str, default=None, metavar='TEXT',
                   help='Search for strings containing TEXT')
    p.add_argument('--stats', action='store_true',
                   help='Show statistics')
    args = p.parse_args()

    data, count, offsets = load_phrase(args.file, args.raw)
    print(f"  Loaded: {len(data):,} bytes, {count} strings\n")

    if args.index is not None:
        idx = int(args.index, 0)
        show_index(data, offsets, idx)
    elif args.range is not None:
        show_range(data, offsets, args.range)
    elif args.search is not None:
        show_search(data, offsets, args.search)
    elif args.stats:
        show_stats(data, offsets, args.file)
    else:
        show_all(data, offsets, args.file)


if __name__ == '__main__':
    main()
