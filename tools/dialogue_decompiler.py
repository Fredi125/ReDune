#!/usr/bin/env python
"""
Dune 1992 DIALOGUE Script Table Decompiler
=============================================
Decompile DIALOGUE.HSQ into human-readable dialogue entry tables.

DIALOGUE.HSQ is NOT a bytecode VM — it's a fixed 4-byte record table that
controls which dialogue options are available for each NPC. Each record
gates a PHRASE text string on a CONDIT condition.

Architecture (decoded from DNCDPRG.EXE sub_19F9E and OpenRakis ASM):
  - Offset table: 136 entries × uint16 LE → dialogue entry lists
  - Each entry: list of 4-byte records, terminated by 0xFFFF
  - Record format (4 bytes):
      byte 0: flags (spoken/repeatable/action code)
        bit 7: "already spoken" (set at runtime, persisted in save)
        bit 6: "repeatable" (can show again after spoken)
        bits 3-0: NPC action code (0-15, jump table at CS:0xA107)
      byte 1: NPC/character ID (also low byte of CONDIT index)
      byte 2: condition type + menu flag + phrase high bits
        bits 7-6: condition type (0=unconditional, 1=CONDIT[256+b1], 2=CONDIT[512+b1])
        bits 3-2: menu option flag (nonzero → clickable dialogue choice)
        bits 1-0: high 2 bits of 10-bit phrase ID
      byte 3: phrase ID low byte

  - Full CONDIT index = (cond_type * 256) + byte1
  - Full phrase ID = ((byte2 & 0x03) << 8) | byte3 (+ 0x800 for PHRASE lookup)

  - NPC.ForDialogue (byte 6 of NPC record at save 0x53F4) indexes
    directly into this entry table.

Usage:
  python dialogue_decompiler.py DIALOGUE.HSQ             # All entries
  python dialogue_decompiler.py DIALOGUE.HSQ --entry 9   # Single entry
  python dialogue_decompiler.py DIALOGUE.HSQ --stats     # Statistics
  python dialogue_decompiler.py DIALOGUE.HSQ --raw       # Already decompressed
"""

import struct
import sys
import argparse
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.compression import hsq_decompress


# =============================================================================
# DIALOGUE RECORD DECODER
# =============================================================================

def decode_record(b0: int, b1: int, b2: int, b3: int) -> dict:
    """
    Decode a 4-byte DIALOGUE record.

    Format (from DNCDPRG.EXE sub_19F9E):
      Byte 0: Flags + action code
        bit 7: "already spoken" (set at runtime, persisted in save)
        bit 6: "repeatable" (can show again)
        bits 5-4: additional flags
        bits 3-0: NPC action code (0-15)
      Byte 1: NPC/character ID (low byte of CONDIT index)
      Byte 2: Condition type + menu flag + phrase high bits
        bits 7-6: condition type (0-3)
        bits 3-2: menu option flag
        bits 1-0: high 2 bits of 10-bit phrase ID
      Byte 3: Phrase ID low byte

    Full CONDIT index = (cond_type * 256) + byte1
    Full phrase ID = ((byte2 & 0x03) << 8) | byte3

    Returns dict with decoded fields.
    """
    # Byte 0: flags + action
    spoken = bool(b0 & 0x80)
    repeatable = bool(b0 & 0x40)
    action_code = b0 & 0x0F

    # Byte 1: NPC ID / CONDIT low byte
    npc_id = b1

    # Byte 2: condition type + menu + phrase high
    cond_type = (b2 >> 6) & 0x03
    menu_flag = (b2 >> 2) & 0x03
    condit_idx = cond_type * 256 + b1  # full CONDIT index

    # Phrase ID: 10-bit from byte2 bits 1-0 + byte3
    phrase_idx = ((b2 & 0x03) << 8) | b3

    return {
        'spoken': spoken,
        'repeatable': repeatable,
        'action_code': action_code,
        'npc_id': npc_id,
        'cond_type': cond_type,
        'condit_idx': condit_idx,
        'menu_flag': menu_flag,
        'phrase_idx': phrase_idx,
        'cond_flags': b0,  # kept for backward compat
        'raw': (b0, b1, b2, b3),
    }


def flags_str(rec: dict) -> str:
    """Format record flags as readable string."""
    parts = []
    if rec['spoken']:
        parts.append("SPOKEN")
    if rec['repeatable']:
        parts.append("REPEAT")
    if rec['action_code']:
        parts.append(f"act={rec['action_code']}")
    if rec['menu_flag']:
        parts.append(f"menu={rec['menu_flag']}")
    b0 = rec['cond_flags']
    if b0 & 0x20:
        parts.append("0x20")
    if b0 & 0x10:
        parts.append("0x10")
    return '|'.join(parts) if parts else "none"


def cond_type_str(cond_type: int) -> str:
    """Format condition type."""
    if cond_type == 0:
        return "unconditional"
    return f"type{cond_type}"


# =============================================================================
# FILE PARSER
# =============================================================================

def load_dialogue(path: str, is_raw: bool = False) -> tuple:
    """
    Load DIALOGUE data from HSQ or raw binary file.

    Returns: (data_bytes, entry_count, offsets_list)
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
        raise ValueError("DIALOGUE file too short")

    # Parse offset table
    first_offset = struct.unpack_from('<H', data, 0)[0]
    entry_count = first_offset // 2

    offsets = []
    for i in range(entry_count):
        if i * 2 + 1 >= len(data):
            break
        offsets.append(struct.unpack_from('<H', data, i * 2)[0])

    return bytes(data), entry_count, offsets


def parse_entry(data: bytes, start: int) -> list:
    """
    Parse all 4-byte records in a dialogue entry.

    Returns list of decoded record dicts. Empty list if entry starts with 0xFFFF.
    """
    records = []
    pos = start

    while pos + 1 < len(data):
        # Check for FF FF terminator
        word0 = struct.unpack_from('<H', data, pos)[0]
        if word0 == 0xFFFF:
            break

        if pos + 3 >= len(data):
            break

        b0, b1, b2, b3 = data[pos], data[pos + 1], data[pos + 2], data[pos + 3]
        records.append(decode_record(b0, b1, b2, b3))
        pos += 4

    return records


# =============================================================================
# DISPLAY MODES
# =============================================================================

def show_entry(data: bytes, offsets: list, idx: int):
    """Show detailed view of a single dialogue entry."""
    if idx < 0 or idx >= len(offsets):
        print(f"Entry {idx} out of range (0-{len(offsets) - 1})")
        return

    start = offsets[idx]
    records = parse_entry(data, start)

    if not records:
        print(f"Entry {idx}: (empty — FF FF terminator)")
        return

    print(f"Entry {idx} @ 0x{start:04X} ({len(records)} records):")
    print(f"  {'#':>3}  {'Raw':12}  {'CondType':>8}  {'CONDIT':>8}  {'Phrase':>6}  {'Flags'}")
    print(f"  {'---':>3}  {'--------':12}  {'--------':>8}  {'--------':>8}  {'------':>6}  {'-----'}")

    for i, rec in enumerate(records):
        b0, b1, b2, b3 = rec['raw']
        raw_hex = f"{b0:02X} {b1:02X} {b2:02X} {b3:02X}"
        ct = cond_type_str(rec['cond_type'])
        ci = f"[{rec['condit_idx']:3d}]"
        pi = f"0x{rec['phrase_idx']:03X}"
        fl = flags_str(rec)
        print(f"  {i:3d}  {raw_hex:12}  {ct:>8}  {ci:>8}  {pi:>6}  {fl}")


def show_all(data: bytes, offsets: list):
    """Show compact view of all dialogue entries."""
    for idx in range(len(offsets)):
        start = offsets[idx]
        records = parse_entry(data, start)

        if not records:
            continue

        # Compact format: entry index, record count, first/last phrase
        first_phrase = records[0]['phrase_idx']
        last_phrase = records[-1]['phrase_idx']
        condit_indices = sorted(set(r['condit_idx'] for r in records))
        cond_types = sorted(set(r['cond_type'] for r in records))

        condit_range = f"{condit_indices[0]:3d}"
        if len(condit_indices) > 1:
            condit_range += f"-{condit_indices[-1]:3d}"

        types_str = ','.join(str(t) for t in cond_types)

        print(f"[{idx:3d}] @0x{start:04X} {len(records):3d} recs  "
              f"condit={condit_range:<9s}  "
              f"phrase=0x{first_phrase:03X}-0x{last_phrase:03X}  "
              f"ctype={types_str}")


def show_full(data: bytes, offsets: list):
    """Show full decompilation of all entries."""
    for idx in range(len(offsets)):
        start = offsets[idx]
        records = parse_entry(data, start)

        if not records:
            continue

        print(f"\n=== Entry {idx} @ 0x{start:04X} ({len(records)} records) ===")
        for i, rec in enumerate(records):
            ct_str = cond_type_str(rec['cond_type'])
            fl_str = flags_str(rec)
            print(f"  [{i:2d}] CONDIT[{rec['condit_idx']:3d}] ({ct_str}) "
                  f"→ phrase[0x{rec['phrase_idx']:03X}]"
                  f"  {fl_str}")


def show_stats(data: bytes, offsets: list):
    """Show dialogue statistics."""
    total_records = 0
    non_empty = 0
    condit_refs = {}
    phrase_refs = {}
    cond_type_usage = {}
    action_usage = {}
    repeatable_count = 0
    menu_count = 0

    for idx in range(len(offsets)):
        start = offsets[idx]
        records = parse_entry(data, start)

        if not records:
            continue

        non_empty += 1
        total_records += len(records)

        for rec in records:
            ci = rec['condit_idx']
            condit_refs[ci] = condit_refs.get(ci, 0) + 1

            pi = rec['phrase_idx']
            phrase_refs[pi] = phrase_refs.get(pi, 0) + 1

            ct = rec['cond_type']
            cond_type_usage[ct] = cond_type_usage.get(ct, 0) + 1

            ac = rec['action_code']
            action_usage[ac] = action_usage.get(ac, 0) + 1

            if rec['repeatable']:
                repeatable_count += 1
            if rec['menu_flag']:
                menu_count += 1

    print(f"=== DIALOGUE Statistics ===")
    print(f"  Total entries:       {len(offsets)}")
    print(f"  Non-empty entries:   {non_empty}")
    print(f"  Empty entries:       {len(offsets) - non_empty}")
    print(f"  Total records:       {total_records}")
    print(f"  Avg records/entry:   {total_records / non_empty:.1f}" if non_empty else "")
    print(f"  Data size:           {len(data):,} bytes")

    print(f"\n  Condition type distribution:")
    for ct in sorted(cond_type_usage):
        label = "unconditional" if ct == 0 else f"type {ct} (CONDIT[{ct*256}..{ct*256+255}])"
        print(f"    {label}: {cond_type_usage[ct]} records")

    print(f"\n  Repeatable records:  {repeatable_count}")
    print(f"  One-shot records:    {total_records - repeatable_count}")
    print(f"  Menu option records: {menu_count}")

    print(f"\n  Action code distribution:")
    for ac in sorted(action_usage, key=lambda x: -action_usage[x]):
        label = "no action" if ac == 0 else f"action {ac}"
        print(f"    {label}: {action_usage[ac]} records")

    print(f"\n  Unique CONDIT indices: {len(condit_refs)}")
    print(f"  CONDIT index range: {min(condit_refs)}-{max(condit_refs)}")

    print(f"\n  Top referenced CONDIT conditions:")
    for ci, count in sorted(condit_refs.items(), key=lambda x: -x[1])[:15]:
        ct = ci // 256
        lo = ci % 256
        print(f"    CONDIT[{ci:3d}] (type{ct}:0x{lo:02X}): {count} references")

    print(f"\n  Unique phrase indices: {len(phrase_refs)}")
    print(f"  Phrase index range: 0x{min(phrase_refs):03X}-0x{max(phrase_refs):03X}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 DIALOGUE Script Table Decompiler',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file', help='DIALOGUE.HSQ or decompressed binary')
    p.add_argument('--raw', action='store_true',
                   help='Input is already decompressed')
    p.add_argument('--entry', type=int, default=None, metavar='N',
                   help='Show single entry in detail')
    p.add_argument('--full', action='store_true',
                   help='Show full decompilation of all entries')
    p.add_argument('--stats', action='store_true',
                   help='Show statistics')
    args = p.parse_args()

    data, count, offsets = load_dialogue(args.file, args.raw)
    print(f"  Loaded: {len(data):,} bytes, {count} entries\n")

    if args.entry is not None:
        show_entry(data, offsets, args.entry)
    elif args.full:
        show_full(data, offsets)
    elif args.stats:
        show_stats(data, offsets)
    else:
        show_all(data, offsets)


if __name__ == '__main__':
    main()
