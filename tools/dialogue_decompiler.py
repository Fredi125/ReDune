#!/usr/bin/env python3
"""
Dune 1992 DIALOGUE Bytecode Decompiler
=========================================
Decompile DIALOGUE.HSQ into human-readable dialogue entry tables.

DIALOGUE.HSQ controls which dialogue options are available for each NPC
at any point in the game. It maps CONDIT condition indices to PHRASE
text string indices.

Architecture (decoded from DNCDPRG.EXE CS1:0xCFC0+ and OpenRakis ASM):
  - Offset table: 136 entries × uint16 LE → dialogue entry lists
  - Each entry: list of 4-byte records, terminated by 0xFFFF
  - Record format (4 bytes = 2 words):
      word0 (LE): flags_lo | (condit_index << 8)
      word1 (LE): phrase_flags_and_bank | (phrase_index_hi << 8)
  - Phrase index extraction (from ASM):
      raw = (byte2 << 8) | byte3  (after xchg al,ah)
      phrase_idx = (raw & 0x3FF) - 1
      phrase_bank = byte2 & 0x03  (selects PHRASE file pair)
      phrase_flags = byte2 & 0xFC (upper 6 bits)

  - NPC.ForDialogue (byte 6 of NPC record at save 0x53F4) indexes
    directly into this entry table.
  - Each record gates a dialogue phrase on a CONDIT condition.

Usage:
  python3 dialogue_decompiler.py DIALOGUE.HSQ             # All entries
  python3 dialogue_decompiler.py DIALOGUE.HSQ --entry 9   # Single entry
  python3 dialogue_decompiler.py DIALOGUE.HSQ --stats     # Statistics
  python3 dialogue_decompiler.py DIALOGUE.HSQ --raw       # Already decompressed
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

    Format (from DNCDPRG.EXE disassembly):
      Byte 0: Condition flags / type
      Byte 1: CONDIT condition index (0x00-0xFF)
      Byte 2: Phrase flags (bits 2-7) + phrase bank (bits 0-1)
      Byte 3: Phrase index low byte

    Phrase index extraction (ASM at CS1:0xCFCE):
      mov ax, [si+2]    ; uint16 LE = byte2 | (byte3 << 8)
      xchg al, ah       ; swap → (byte2 << 8) | byte3
      and ax, 3FFh       ; mask to 10 bits
      dec ax             ; subtract 1

    Returns dict with decoded fields.
    """
    # Word 0: condition info
    cond_flags = b0
    condit_idx = b1

    # Word 1: phrase info
    # After byte-swap: (byte2 << 8) | byte3, then mask 0x3FF, then -1
    raw_phrase = ((b2 << 8) | b3) & 0x3FF
    phrase_idx = raw_phrase - 1 if raw_phrase > 0 else 0
    phrase_bank = b2 & 0x03   # selects PHRASE1x vs PHRASE2x
    phrase_flags = b2 & 0xFC  # upper 6 bits are flags

    return {
        'cond_flags': cond_flags,
        'condit_idx': condit_idx,
        'phrase_idx': phrase_idx,
        'phrase_bank': phrase_bank,
        'phrase_flags': phrase_flags,
        'raw': (b0, b1, b2, b3),
    }


def cond_flags_str(flags: int) -> str:
    """Format condition flags byte as readable string."""
    if flags == 0x00:
        return "always"
    parts = []
    if flags & 0x40:
        parts.append("GATE")
    if flags & 0x20:
        parts.append("0x20")
    if flags & 0x0F:
        parts.append(f"lo=0x{flags & 0x0F:X}")
    if flags & 0x80:
        parts.append("0x80")
    if flags & 0x10:
        parts.append("0x10")
    return '|'.join(parts) if parts else f"0x{flags:02X}"


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
    print(f"  {'#':>3}  {'Raw':12}  {'CondFlg':>7}  {'Condit':>6}  {'Bank':>4}  {'Phrase':>6}  {'PhrFlg':>6}")
    print(f"  {'---':>3}  {'--------':12}  {'-------':>7}  {'------':>6}  {'----':>4}  {'------':>6}  {'------':>6}")

    for i, rec in enumerate(records):
        b0, b1, b2, b3 = rec['raw']
        raw_hex = f"{b0:02X} {b1:02X} {b2:02X} {b3:02X}"
        cf = f"0x{rec['cond_flags']:02X}"
        ci = f"0x{rec['condit_idx']:02X}"
        bank = str(rec['phrase_bank'])
        pi = f"0x{rec['phrase_idx']:03X}"
        pf = f"0x{rec['phrase_flags']:02X}" if rec['phrase_flags'] else "  -"
        print(f"  {i:3d}  {raw_hex:12}  {cf:>7}  {ci:>6}  {bank:>4}  {pi:>6}  {pf:>6}")


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

        condit_range = f"0x{condit_indices[0]:02X}"
        if len(condit_indices) > 1:
            condit_range += f"-0x{condit_indices[-1]:02X}"

        banks = sorted(set(r['phrase_bank'] for r in records))
        bank_str = ','.join(str(b) for b in banks)

        print(f"[{idx:3d}] @0x{start:04X} {len(records):3d} recs  "
              f"condit={condit_range:<11s}  "
              f"phrase=0x{first_phrase:03X}-0x{last_phrase:03X}  "
              f"bank={bank_str}")


def show_full(data: bytes, offsets: list):
    """Show full decompilation of all entries."""
    for idx in range(len(offsets)):
        start = offsets[idx]
        records = parse_entry(data, start)

        if not records:
            continue

        print(f"\n=== Entry {idx} @ 0x{start:04X} ({len(records)} records) ===")
        for i, rec in enumerate(records):
            b0, b1, b2, b3 = rec['raw']
            cf_str = cond_flags_str(rec['cond_flags'])
            print(f"  [{i:2d}] condit[0x{rec['condit_idx']:02X}] "
                  f"→ phrase[bank{rec['phrase_bank']}:0x{rec['phrase_idx']:03X}]"
                  f"  flags={cf_str}"
                  + (f"  phr_flags=0x{rec['phrase_flags']:02X}" if rec['phrase_flags'] else ""))


def show_stats(data: bytes, offsets: list):
    """Show dialogue statistics."""
    total_records = 0
    non_empty = 0
    condit_refs = {}
    phrase_refs = {}
    bank_usage = {}
    cond_flag_usage = {}
    phrase_flag_usage = {}

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

            bk = rec['phrase_bank']
            bank_usage[bk] = bank_usage.get(bk, 0) + 1

            cf = rec['cond_flags']
            cond_flag_usage[cf] = cond_flag_usage.get(cf, 0) + 1

            pf = rec['phrase_flags']
            if pf:
                phrase_flag_usage[pf] = phrase_flag_usage.get(pf, 0) + 1

    print(f"=== DIALOGUE Statistics ===")
    print(f"  Total entries:       {len(offsets)}")
    print(f"  Non-empty entries:   {non_empty}")
    print(f"  Empty entries:       {len(offsets) - non_empty}")
    print(f"  Total records:       {total_records}")
    print(f"  Avg records/entry:   {total_records / non_empty:.1f}" if non_empty else "")
    print(f"  Data size:           {len(data):,} bytes")

    print(f"\n  Phrase bank usage:")
    for bk in sorted(bank_usage):
        print(f"    Bank {bk}: {bank_usage[bk]} records")

    print(f"\n  Condition flags distribution:")
    for cf in sorted(cond_flag_usage, key=lambda x: -cond_flag_usage[x])[:15]:
        print(f"    0x{cf:02X} ({cond_flags_str(cf):>12s}): {cond_flag_usage[cf]:3d} records")

    if phrase_flag_usage:
        print(f"\n  Phrase flags distribution:")
        for pf in sorted(phrase_flag_usage, key=lambda x: -phrase_flag_usage[x])[:10]:
            print(f"    0x{pf:02X}: {phrase_flag_usage[pf]:3d} records")

    print(f"\n  Unique CONDIT indices referenced: {len(condit_refs)}")
    print(f"  CONDIT index range: 0x{min(condit_refs):02X}-0x{max(condit_refs):02X}")

    print(f"\n  Top referenced CONDIT conditions:")
    for ci, count in sorted(condit_refs.items(), key=lambda x: -x[1])[:15]:
        print(f"    CONDIT[0x{ci:02X}]: {count} references")

    print(f"\n  Unique phrase indices: {len(phrase_refs)}")
    print(f"  Phrase index range: 0x{min(phrase_refs):03X}-0x{max(phrase_refs):03X}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 DIALOGUE Bytecode Decompiler',
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
