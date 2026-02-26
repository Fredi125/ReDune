#!/usr/bin/env python3
"""
Dune 1992 DUNE.DAT Archive Decoder & Repacker

Reads, extracts, and rebuilds DUNE.DAT archives (Cryo Interactive, CD version).

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
  python3 dat_decoder.py DUNE.DAT                       # List all files
  python3 dat_decoder.py DUNE.DAT --stats                # Summary statistics
  python3 dat_decoder.py DUNE.DAT --extract outdir/      # Extract + auto-manifest
  python3 dat_decoder.py DUNE.DAT --find "*.HNM"         # Find files by pattern
  python3 dat_decoder.py DUNE.DAT --info CONDIT.HSQ       # Show info for one file
  python3 dat_decoder.py DUNE.DAT --manifest out.txt      # Export manifest with flags
  python3 dat_decoder.py --repack indir/ -o NEW.DAT -m manifest.txt  # Repack with manifest
  python3 dat_decoder.py --repack indir/ -o NEW.DAT -m m.txt --verify ORIG.DAT  # Repack + verify

Roundtrip workflow (byte-identical):
  1. python3 dat_decoder.py DUNE.DAT --extract gamedata/
     (creates gamedata/manifest.txt with file order, flags, and magic)
  2. python3 dat_decoder.py --repack gamedata/ -o REPACKED.DAT -m gamedata/manifest.txt
  3. python3 dat_decoder.py REPACKED.DAT --verify DUNE.DAT
"""

import argparse
import fnmatch
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress, hsq_compress, hsq_get_sizes

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


def extract_files(entries: list, dat_data: bytes, outdir: str,
                   decompress: bool = False, manifest_path: str = None):
    """Extract all files from the archive.

    When manifest_path is provided, also exports a manifest file preserving
    the exact file ordering and flags for byte-identical roundtrip repacking.
    """
    extracted = 0
    errors = 0

    os.makedirs(outdir, exist_ok=True)

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

    # Export manifest automatically alongside extraction
    if manifest_path:
        magic = struct.unpack_from('<H', dat_data, 0)[0]
        export_manifest(entries, manifest_path, magic=magic)

    print(f"\nExtracted {extracted} files to {outdir}/ ({errors} errors)")


# =============================================================================
# MANIFEST (file ordering)
# =============================================================================

def export_manifest(entries: list, outpath: str, magic: int = 0x0A3D):
    """Export file manifest preserving archive order, flags, and magic.

    Manifest is a plain text file with one entry per line.
    Format: FILENAME [flag=N] (flag omitted when 0)
    First non-comment line starting with 'magic=' stores the header magic value.
    Comments (# ...) and blank lines are allowed on import.
    """
    with open(outpath, 'w') as f:
        f.write("# DUNE.DAT manifest — file order and metadata for repacking\n")
        f.write(f"# {len(entries)} files\n")
        f.write(f"magic=0x{magic:04X}\n")
        for entry in entries:
            if entry.get('flag', 0) != 0:
                f.write(f"{entry['name']}\tflag={entry['flag']}\n")
            else:
                f.write(f"{entry['name']}\n")
    print(f"Exported manifest: {len(entries)} files -> {outpath} (magic=0x{magic:04X})")


def load_manifest(path: str) -> tuple:
    """Load file manifest with flags and magic.

    Returns:
        (entries, magic) where entries is list of {'name': str, 'flag': int}
        and magic is the header magic value (or None if not in manifest).
    """
    entries = []
    magic = None
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Parse magic= directive
            if line.startswith('magic='):
                magic = int(line.split('=', 1)[1], 0)
                continue
            # Parse "FILENAME\tflag=N" or just "FILENAME"
            parts = line.split('\t')
            name = parts[0]
            flag = 0
            for part in parts[1:]:
                if part.startswith('flag='):
                    flag = int(part.split('=', 1)[1])
            entries.append({'name': name, 'flag': flag})
    return entries, magic


# =============================================================================
# REPACK (directory → DUNE.DAT)
# =============================================================================

def collect_files(indir: str, manifest_entries: list = None) -> list:
    """Collect files from directory for repacking.

    If manifest_entries is provided (list of {'name', 'flag'} dicts),
    uses that ordering and flags. Otherwise, collects all files
    alphabetically (uppercase names) with flag=0.

    Returns list of (archive_name, local_path, flag) tuples.
    """
    if manifest_entries:
        files = []
        for entry in manifest_entries:
            name = entry['name']
            flag = entry.get('flag', 0)
            # Archive names use backslash for subdirs
            local_name = name.replace('\\', os.sep)
            local_path = os.path.join(indir, local_name)
            if os.path.isfile(local_path):
                files.append((name, local_path, flag))
            else:
                print(f"  WARNING: manifest file not found: {name} ({local_path})",
                      file=sys.stderr)
        return files

    # No manifest: scan directory recursively, build archive names
    files = []
    for dirpath, dirnames, filenames in os.walk(indir):
        # Skip hidden files/dirs
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for fname in sorted(filenames):
            if fname.startswith('.'):
                continue
            local_path = os.path.join(dirpath, fname)
            # Build archive name relative to indir, with DOS backslash separators
            rel = os.path.relpath(local_path, indir)
            archive_name = rel.replace(os.sep, '\\').upper()
            files.append((archive_name, local_path, 0))

    # Sort by archive name (uppercase)
    files.sort(key=lambda x: x[0])
    return files


def build_dat(files: list, outpath: str, count_hint: int = 0x0A3D):
    """Build a DUNE.DAT archive from a list of (archive_name, local_path, flag) tuples.

    File data is aligned to 16-byte boundaries, matching the original DUNE.DAT layout.

    Args:
        files: List of (archive_name, local_path, flag) tuples
        outpath: Output DUNE.DAT path
        count_hint: Version/magic uint16 (default 0x0A3D for CD v3.7)
    """
    # Validate: entries must fit in header
    # Header: 2 (count) + N*25 (entries) + 1 (terminator) <= 0x10000
    max_entries = (HEADER_SIZE - 3) // ENTRY_SIZE
    if len(files) > max_entries:
        raise ValueError(f"Too many files: {len(files)} (max {max_entries} for 64KB header)")

    # Validate: filenames must fit in 16 bytes
    for name, _, _flag in files:
        encoded = name.encode('ascii')
        if len(encoded) > 15:  # 15 chars + null terminator
            raise ValueError(f"Filename too long (max 15 chars): {name}")

    # Read all file data
    print(f"Reading {len(files)} files...")
    file_data_list = []
    total_data_size = 0
    for name, local_path, _flag in files:
        with open(local_path, 'rb') as f:
            data = f.read()
        file_data_list.append(data)
        total_data_size += len(data)

    # Build header
    header = bytearray(HEADER_SIZE)
    struct.pack_into('<H', header, 0, count_hint)

    pos = 2
    data_offset = HEADER_SIZE  # data starts after 64KB header (already 16-byte aligned)

    entries_written = 0
    for i, (name, _, flag) in enumerate(files):
        file_data = file_data_list[i]

        # Write 16-byte filename (null-padded)
        name_bytes = name.encode('ascii')
        header[pos:pos + len(name_bytes)] = name_bytes
        # Remaining bytes already zero (null padding)

        # Write size and offset
        struct.pack_into('<i', header, pos + 16, len(file_data))
        struct.pack_into('<i', header, pos + 20, data_offset)
        header[pos + 24] = flag  # preserve original flag

        # Advance offset past file data, then align to 16-byte boundary
        data_offset += len(file_data)
        data_offset = (data_offset + 15) & ~15  # align to next 16-byte boundary

        pos += ENTRY_SIZE
        entries_written += 1

    # Terminator: name[0] == 0x00 (already zero in bytearray)

    # Write output file with 16-byte alignment padding between files
    with open(outpath, 'wb') as f:
        f.write(header)
        for i, data in enumerate(file_data_list):
            f.write(data)
            # Pad to 16-byte boundary between files (not after last file)
            if i < len(file_data_list) - 1:
                remainder = len(data) % 16
                if remainder != 0:
                    f.write(b'\x00' * (16 - remainder))

    archive_size = os.path.getsize(outpath)
    print(f"\nBuilt DUNE.DAT: {outpath}")
    print(f"  Files: {entries_written}")
    print(f"  Magic: 0x{count_hint:04X}")
    print(f"  Header: {HEADER_SIZE:,} bytes (64KB)")
    print(f"  Data: {archive_size - HEADER_SIZE:,} bytes ({(archive_size - HEADER_SIZE) / 1024 / 1024:.1f} MB)")
    print(f"  Total: {archive_size:,} bytes ({archive_size / 1024 / 1024:.1f} MB)")
    print(f"  Alignment: 16-byte boundaries")


def repack(indir: str, outpath: str, manifest_path: str = None):
    """Repack a directory of files into a DUNE.DAT archive.

    Args:
        indir: Directory containing game files
        outpath: Output DUNE.DAT path
        manifest_path: Optional manifest file for ordering
    """
    manifest_entries = None
    magic = 0x0A3D  # default for CD v3.7
    if manifest_path:
        manifest_entries, manifest_magic = load_manifest(manifest_path)
        if manifest_magic is not None:
            magic = manifest_magic
        print(f"Using manifest: {manifest_path} ({len(manifest_entries)} files, magic=0x{magic:04X})")

    files = collect_files(indir, manifest_entries)
    if not files:
        print("No files found to pack.", file=sys.stderr)
        return 1

    print(f"Collected {len(files)} files from {indir}/")
    build_dat(files, outpath, count_hint=magic)
    return 0


# =============================================================================
# REPLACE (swap single file in archive)
# =============================================================================

def replace_file(dat_path: str, name: str, replacement_path: str, outpath: str):
    """Replace a single file in a DUNE.DAT archive.

    Rebuilds the archive with the specified file replaced. All other files,
    file ordering, and 16-byte alignment are preserved.

    Args:
        dat_path: Original DUNE.DAT path
        name: Archive filename to replace (e.g. "CONDIT.HSQ")
        replacement_path: Path to replacement file data
        outpath: Output DUNE.DAT path
    """
    dat_data = open(dat_path, 'rb').read()
    entries = parse_dat_header(dat_data)

    # Find the target entry
    target_idx = None
    for i, entry in enumerate(entries):
        if entry['name'].upper() == name.upper():
            target_idx = i
            break
    if target_idx is None:
        print(f"File not found in archive: {name}", file=sys.stderr)
        return 1

    # Read replacement data
    with open(replacement_path, 'rb') as f:
        new_data = f.read()

    old_size = entries[target_idx]['size']
    print(f"Replacing {name}: {old_size:,} -> {len(new_data):,} bytes")

    # Rebuild archive with 16-byte alignment
    header = bytearray(HEADER_SIZE)
    struct.pack_into('<H', header, 0, struct.unpack_from('<H', dat_data, 0)[0])

    pos = 2
    data_offset = HEADER_SIZE
    data_chunks = []

    for i, entry in enumerate(entries):
        if i == target_idx:
            file_data = new_data
        else:
            file_data = dat_data[entry['offset']:entry['offset'] + entry['size']]

        # Write header entry
        name_bytes = entry['name'].encode('ascii')
        header[pos:pos + len(name_bytes)] = name_bytes
        struct.pack_into('<i', header, pos + 16, len(file_data))
        struct.pack_into('<i', header, pos + 20, data_offset)
        header[pos + 24] = entry['flag']

        data_chunks.append(file_data)
        # Advance offset past file data, then align to 16-byte boundary
        data_offset += len(file_data)
        data_offset = (data_offset + 15) & ~15
        pos += ENTRY_SIZE

    with open(outpath, 'wb') as f:
        f.write(header)
        for i, chunk in enumerate(data_chunks):
            f.write(chunk)
            # Pad to 16-byte boundary between files (not after last file)
            if i < len(data_chunks) - 1:
                remainder = len(chunk) % 16
                if remainder != 0:
                    f.write(b'\x00' * (16 - remainder))

    total = os.path.getsize(outpath)
    print(f"Written: {outpath} ({total:,} bytes)")
    return 0


# =============================================================================
# VERIFY (roundtrip check)
# =============================================================================

def verify_dat(original_path: str, repacked_path: str) -> int:
    """Verify a repacked DAT is byte-identical to the original.

    Returns 0 if identical, 1 if different.
    """
    orig_data = open(original_path, 'rb').read()
    repack_data = open(repacked_path, 'rb').read()

    if orig_data == repack_data:
        print(f"VERIFY OK: {repacked_path} is byte-identical to {original_path}")
        return 0

    # Report differences
    issues = []

    # Size
    if len(orig_data) != len(repack_data):
        issues.append(f"Size: {len(orig_data):,} vs {len(repack_data):,}")

    # Magic
    orig_magic = struct.unpack_from('<H', orig_data, 0)[0]
    repack_magic = struct.unpack_from('<H', repack_data, 0)[0]
    if orig_magic != repack_magic:
        issues.append(f"Magic: 0x{orig_magic:04X} vs 0x{repack_magic:04X}")

    # Parse entries
    orig_entries = parse_dat_header(orig_data)
    repack_entries = parse_dat_header(repack_data)

    if len(orig_entries) != len(repack_entries):
        issues.append(f"Entry count: {len(orig_entries)} vs {len(repack_entries)}")

    # Compare entries
    n = min(len(orig_entries), len(repack_entries))
    order_diffs = flag_diffs = data_diffs = 0
    for i in range(n):
        oe, re = orig_entries[i], repack_entries[i]
        if oe['name'] != re['name']:
            order_diffs += 1
        if oe['flag'] != re['flag']:
            flag_diffs += 1
        if oe['size'] == re['size']:
            orig_file = orig_data[oe['offset']:oe['offset'] + oe['size']]
            repack_file = repack_data[re['offset']:re['offset'] + re['size']]
            if orig_file != repack_file:
                data_diffs += 1

    if order_diffs:
        issues.append(f"File ordering: {order_diffs} entries in different positions")
    if flag_diffs:
        issues.append(f"Flags: {flag_diffs} entries with different flags")
    if data_diffs:
        issues.append(f"Data: {data_diffs} files with different content")

    # First byte difference
    min_len = min(len(orig_data), len(repack_data))
    for i in range(min_len):
        if orig_data[i] != repack_data[i]:
            region = "header" if i < HEADER_SIZE else "data"
            issues.append(f"First diff at 0x{i:08X} ({region}): "
                         f"0x{orig_data[i]:02X} vs 0x{repack_data[i]:02X}")
            break

    print(f"VERIFY FAILED: {repacked_path} differs from {original_path}")
    for issue in issues:
        print(f"  - {issue}")
    print(f"\nUse dat_compare.py for detailed analysis")
    return 1


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Dune 1992 DUNE.DAT Archive Decoder & Repacker')
    parser.add_argument('datfile', nargs='?', help='Path to DUNE.DAT (or input dir for --repack)')
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
    parser.add_argument('--manifest', metavar='OUTFILE',
                        help='Export file manifest (preserves archive order and flags)')
    parser.add_argument('--repack', metavar='INDIR',
                        help='Repack directory into DUNE.DAT')
    parser.add_argument('--replace', nargs=2, metavar=('NAME', 'FILE'),
                        help='Replace a single file in the archive')
    parser.add_argument('--verify', metavar='ORIGINAL',
                        help='Verify repacked DAT matches original')
    parser.add_argument('-o', '--output', metavar='PATH',
                        help='Output path for --repack or --replace')
    parser.add_argument('-m', '--manifest-file', metavar='PATH',
                        help='Manifest file for --repack ordering')
    args = parser.parse_args()

    # --- Repack mode ---
    if args.repack:
        if not args.output:
            print("--repack requires -o OUTPUT_PATH", file=sys.stderr)
            return 1
        rc = repack(args.repack, args.output, args.manifest_file)
        if rc == 0 and args.verify:
            return verify_dat(args.verify, args.output)
        return rc

    # --- Replace mode ---
    if args.replace:
        if not args.datfile:
            print("--replace requires DUNE.DAT path as first argument", file=sys.stderr)
            return 1
        if not args.output:
            print("--replace requires -o OUTPUT_PATH", file=sys.stderr)
            return 1
        return replace_file(args.datfile, args.replace[0], args.replace[1], args.output)

    # --- Verify mode (standalone) ---
    if args.verify:
        if not args.datfile:
            print("--verify requires REPACKED.DAT as first argument", file=sys.stderr)
            return 1
        return verify_dat(args.verify, args.datfile)

    # --- Read mode (requires datfile) ---
    if not args.datfile:
        parser.print_help()
        return 1

    if not os.path.exists(args.datfile):
        print(f"File not found: {args.datfile}", file=sys.stderr)
        return 1

    # Read file (or just header for listing)
    if args.header_only or (not args.extract and not args.info and not args.manifest):
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

    if args.manifest:
        magic = struct.unpack_from('<H', data, 0)[0]
        export_manifest(entries, args.manifest, magic=magic)
    elif args.stats:
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
        # Auto-export manifest alongside extraction
        manifest_path = os.path.join(args.extract, 'manifest.txt')
        extract_files(entries, data, args.extract, args.decompress,
                     manifest_path=manifest_path)
    else:
        list_files(entries)

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
