#!/usr/bin/env python3
"""
Dune 1992 CONDIT Bytecode Decompiler
======================================
Decompile CONDIT.HSQ event condition bytecodes into human-readable expressions.

The CONDIT system is a stack-based expression evaluator that gates dialogue
options and event triggers based on game state variables.

Architecture (decoded from DNCDPRG.EXE sub_C266/C1DB/C204):
  - Stack-based with DX accumulator register
  - 10 operations: EQ, LT, GT, NE, LE, GE, ADD, SUB, AND, OR
  - Operands: byte/word variables at DS:[XX] or immediate values
  - Separator bytes (0x80-0xFE): push to stack, start sub-expression
  - 0xFF terminator: unwind stack, apply deferred operations
  - Result: non-zero = TRUE (condition met), zero = FALSE

Usage:
  python3 condit_decompiler.py CONDIT.HSQ              # Decompile all (from HSQ)
  python3 condit_decompiler.py CONDIT_dec.bin --raw     # Already decompressed
  python3 condit_decompiler.py CONDIT.HSQ --entry 1     # Single entry
  python3 condit_decompiler.py CONDIT.HSQ --chains      # Show chain structure
  python3 condit_decompiler.py CONDIT.HSQ --groups      # Chain summary
  python3 condit_decompiler.py CONDIT.HSQ --stats       # Statistics
"""

import struct
import sys
import argparse
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.compression import hsq_decompress
from lib.constants import CONDIT_OPS, CONDIT_VARIABLES, GAME_STAGES


# =============================================================================
# OPERAND DECODER (sub_C1DB)
# =============================================================================

def read_operand(data, pos):
    """
    Read one operand from CONDIT bytecode.

    Encoding (from DNCDPRG.EXE sub_C1DB):
      01 XX       → byte variable at DS:[XX]
      00 XX       → word variable at DS:[XX]
      02-7F XX    → word variable at DS:[XX]
      80 XX       → immediate byte value XX
      81-FF XXXX  → immediate word value XXXX (uint16 LE)

    Returns: (text, new_pos, metadata)
    """
    if pos >= len(data):
        return "<EOF>", pos, None

    type_byte = data[pos]
    pos += 1

    if type_byte < 0x80:
        # Variable reference
        if pos >= len(data):
            return "<TRUNC>", pos, None
        idx = data[pos]
        pos += 1
        byte_mode = (type_byte == 0x01)
        # Check for known variable names
        var_name = CONDIT_VARIABLES.get(idx, f"0x{idx:02X}")
        prefix = "byte" if byte_mode else "word"
        return f"{prefix}[{var_name}]", pos, ('var', idx, byte_mode)
    elif type_byte == 0x80:
        # Immediate byte
        if pos >= len(data):
            return "<TRUNC>", pos, None
        val = data[pos]
        pos += 1
        return f"0x{val:02X}", pos, ('imm8', val)
    else:
        # Immediate word
        if pos + 1 >= len(data):
            return "<TRUNC>", pos, None
        val = struct.unpack_from('<H', data, pos)[0]
        pos += 2
        return f"0x{val:04X}", pos, ('imm16', val)


# =============================================================================
# EXPRESSION DECOMPILER (sub_C266)
# =============================================================================

def decompile_entry(data, start, annotate=True):
    """
    Decompile one CONDIT entry starting at `start`.

    Execution model:
      1. Read first operand → accumulator
      2. Loop:
         - byte < 0x80: inline op + operand, apply immediately
         - byte 0x80-0xFE: push (acc, deferred_op) to stack, new sub-expression
         - byte 0xFF: break
      3. Unwind stack: for each (left, op): acc = op(left, acc)
      4. Return: acc != 0 → TRUE

    Returns: (expression_str, end_pos)
    """
    pos = start
    stack = []

    # Read first operand
    acc_text, pos, acc_meta = read_operand(data, pos)

    while pos < len(data):
        b = data[pos]
        pos += 1

        if b == 0xFF:
            # Terminator
            break
        elif b >= 0x80:
            # Separator: push current expression, start new sub-expression
            op_idx = b & 0x1F
            op_info = CONDIT_OPS.get(op_idx)
            op_sym = op_info[1] if op_info else f"?{op_idx}"
            stack.append((acc_text, op_sym))
            acc_text, pos, acc_meta = read_operand(data, pos)
        else:
            # Inline operation: apply immediately
            op_idx = b & 0x1F
            op_info = CONDIT_OPS.get(op_idx)
            op_sym = op_info[1] if op_info else f"?{op_idx}"
            rhs_text, pos, rhs_meta = read_operand(data, pos)

            # Annotate GameStage comparisons
            annotation = ""
            if annotate and op_sym == "==" and rhs_meta:
                if acc_meta and acc_meta[0] == 'var' and acc_meta[1] == 0x2A:
                    if rhs_meta[0] in ('imm8', 'imm16'):
                        stage_name = GAME_STAGES.get(rhs_meta[1], None)
                        if stage_name:
                            annotation = f"/*{stage_name}*/"
                elif rhs_meta[0] == 'var' and rhs_meta[1] == 0x2A:
                    pass  # reverse comparison

            if annotation:
                acc_text = f"{acc_text} {op_sym} {rhs_text}{annotation}"
            else:
                acc_text = f"{acc_text} {op_sym} {rhs_text}"

    # Unwind stack
    while stack:
        left_text, op_sym = stack.pop()
        acc_text = f"({left_text}) {op_sym} ({acc_text})"

    return acc_text, pos


# =============================================================================
# FILE PARSER
# =============================================================================

def load_condit(path, is_raw=False):
    """
    Load CONDIT data from HSQ or raw binary file.

    Returns: (data_bytes, entry_count, offsets_list)
    """
    with open(path, 'rb') as f:
        raw = f.read()

    if not is_raw:
        try:
            data = hsq_decompress(raw)
        except Exception:
            print(f"  HSQ decompression failed, treating as raw binary")
            data = raw
    else:
        data = raw

    # Parse offset table
    if len(data) < 2:
        raise ValueError("CONDIT file too short")

    first_offset = struct.unpack_from('<H', data, 0)[0]
    entry_count = first_offset // 2

    offsets = []
    for i in range(entry_count):
        if i * 2 + 1 >= len(data):
            break
        offsets.append(struct.unpack_from('<H', data, i * 2)[0])

    return bytes(data), entry_count, offsets


# =============================================================================
# DISPLAY MODES
# =============================================================================

def show_entry(data, offsets, idx, annotate=True):
    """Decompile and print a single CONDIT entry."""
    if idx < 0 or idx >= len(offsets):
        print(f"Entry {idx} out of range (0-{len(offsets)-1})")
        return

    off = offsets[idx]
    table_end = offsets[idx + 1] if idx + 1 < len(offsets) else len(data)
    chunk = data[off:table_end]

    if all(b == 0 for b in chunk):
        print(f"Entry {idx}: (empty/padding)")
        return

    expr, end_pos = decompile_entry(data, off, annotate)
    overflow = end_pos > table_end

    print(f"Entry {idx}:")
    print(f"  Offset:  0x{off:04X} (table size: {table_end - off}b, exec size: {end_pos - off}b{'  OVERFLOW' if overflow else ''})")
    print(f"  Raw:     {' '.join(f'{data[off+i]:02X}' for i in range(min(end_pos - off, 64)))}")
    if end_pos - off > 64:
        print(f"           ... ({end_pos - off} bytes total)")
    print(f"  Expr:    {expr}")


def show_all(data, offsets, annotate=True):
    """Decompile all non-empty CONDIT entries."""
    for i in range(len(offsets)):
        off = offsets[i]
        table_end = offsets[i + 1] if i + 1 < len(offsets) else len(data)
        chunk = data[off:table_end]
        if all(b == 0 for b in chunk):
            continue
        expr, end_pos = decompile_entry(data, off, annotate)
        overflow = end_pos > table_end
        ov = " [OV]" if overflow else ""
        print(f"[{i:3d}] @0x{off:04X} ({end_pos - off:3d}b){ov}: {expr}")


def show_chains(data, offsets):
    """Show bytecode chain structure (shared bytecode groups)."""
    # Group entries by their execution endpoint
    groups = {}
    for i in range(len(offsets)):
        off = offsets[i]
        table_end = offsets[i + 1] if i + 1 < len(offsets) else len(data)
        chunk = data[off:table_end]
        if all(b == 0 for b in chunk):
            continue
        _, end_pos = decompile_entry(data, off, annotate=False)
        groups.setdefault(end_pos, []).append(i)

    print(f"=== CONDIT Bytecode Chains ===")
    print(f"Total: {len(groups)} chains from {len(offsets)} entries\n")

    for chain_idx, end_pos in enumerate(sorted(groups.keys())):
        entries = groups[end_pos]
        first_off = offsets[entries[0]]
        size = end_pos - first_off
        print(f"Chain #{chain_idx}: @0x{first_off:04X}-0x{end_pos:04X} ({size}b) — {len(entries)} entries")
        for e in entries:
            off = offsets[e]
            _, ep = decompile_entry(data, off, annotate=False)
            print(f"  [{e:3d}] @0x{off:04X} ({ep - off}b)")
        print()


def show_groups(data, offsets):
    """Show chain summary (compact)."""
    groups = {}
    for i in range(len(offsets)):
        off = offsets[i]
        table_end = offsets[i + 1] if i + 1 < len(offsets) else len(data)
        chunk = data[off:table_end]
        if all(b == 0 for b in chunk):
            continue
        _, end_pos = decompile_entry(data, off, annotate=False)
        groups.setdefault(end_pos, []).append(i)

    print(f"{'Chain':>5}  {'Range':>17}  {'Size':>6}  {'Entries':>7}  {'First':>5}–{'Last':>5}")
    print(f"{'-----':>5}  {'-'*17:>17}  {'------':>6}  {'-------':>7}  {'-'*5:>5} {'-'*5:>5}")
    for idx, end_pos in enumerate(sorted(groups.keys())):
        entries = groups[end_pos]
        first_off = offsets[entries[0]]
        size = end_pos - first_off
        print(f"{idx:5d}  0x{first_off:04X}–0x{end_pos:04X}  {size:5d}b  {len(entries):7d}  {entries[0]:5d}–{entries[-1]:5d}")


def show_stats(data, offsets):
    """Show bytecode statistics."""
    non_empty = 0
    sizes = []
    var_refs = {}

    for i in range(len(offsets)):
        off = offsets[i]
        table_end = offsets[i + 1] if i + 1 < len(offsets) else len(data)
        chunk = data[off:table_end]
        if all(b == 0 for b in chunk):
            continue
        non_empty += 1
        _, end_pos = decompile_entry(data, off, annotate=False)
        sizes.append(end_pos - off)

        # Count variable references in the bytecode
        p = off
        while p < end_pos and p < len(data):
            b = data[p]
            if b < 0x80 and p + 1 < len(data):
                var_refs[data[p + 1]] = var_refs.get(data[p + 1], 0) + 1
            p += 1

    print(f"=== CONDIT Statistics ===")
    print(f"  Total entries:     {len(offsets)}")
    print(f"  Non-empty:         {non_empty}")
    print(f"  Empty/padding:     {len(offsets) - non_empty}")
    print(f"  Bytecode area:     0x{offsets[0]:04X}–0x{len(data):04X} ({len(data) - offsets[0]:,} bytes)")
    if sizes:
        print(f"  Entry sizes:       {min(sizes)}–{max(sizes)} bytes (avg {sum(sizes)/len(sizes):.1f})")
    print(f"\n  Top referenced variables:")
    for var, count in sorted(var_refs.items(), key=lambda x: -x[1])[:15]:
        name = CONDIT_VARIABLES.get(var, f"0x{var:02X}")
        print(f"    DS:[{name}]: {count} references")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 CONDIT Bytecode Decompiler',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file', help='CONDIT.HSQ or decompressed binary')
    p.add_argument('--raw', action='store_true', help='Input is already decompressed')
    p.add_argument('--entry', type=int, default=None, metavar='N', help='Decompile single entry')
    p.add_argument('--chains', action='store_true', help='Show chain structure (detailed)')
    p.add_argument('--groups', action='store_true', help='Show chain summary (compact)')
    p.add_argument('--stats', action='store_true', help='Show statistics')
    p.add_argument('--no-annotate', action='store_true', help='Disable GameStage annotations')
    args = p.parse_args()

    data, count, offsets = load_condit(args.file, args.raw)
    print(f"  Loaded: {len(data):,} bytes, {count} entries\n")

    annotate = not args.no_annotate

    if args.entry is not None:
        show_entry(data, offsets, args.entry, annotate)
    elif args.chains:
        show_chains(data, offsets)
    elif args.groups:
        show_groups(data, offsets)
    elif args.stats:
        show_stats(data, offsets)
    else:
        show_all(data, offsets, annotate)


if __name__ == '__main__':
    main()
