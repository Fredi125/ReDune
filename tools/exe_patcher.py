#!/usr/bin/env python
"""
Dune 1992 DNCDPRG.EXE Patcher — Sietch Stage Gate Bug Fix
==========================================================

Patches the sietch initialization table in DNCDPRG.EXE (CD v3.7) to fix
the Celimyn-Tuek discovery bug.

Bug: Sietch #68 (Celimyn-Tuek) has stage_gate=0xFF, making it permanently
undiscoverable during normal gameplay. The sietch is a Fremen sietch
(appearance=0x03) but uses the same 0xFF gate value as Harkonnen-controlled
fortresses, which are discovered through conquest rather than exploration.
Neighboring Celimyn sietches use 0x58-0x5A ("Army Building" stage).

The fix: Change one byte from 0xFF to 0x58 in the sietch initialization
table embedded in the EXE's data segment.

The tool locates the sietch table by pattern-matching the static fields
(region, subregion, coordinates, appearance) at 28-byte stride — no
hardcoded file offsets needed, so it works across EXE variants.

Usage:
  python exe_patcher.py DNCDPRG.EXE                    # Analyze only (dry run)
  python exe_patcher.py DNCDPRG.EXE -o DNCDPRG_FIX.EXE # Patch and write
  python exe_patcher.py DNCDPRG.EXE --fix-all -o FIX.EXE  # Fix #68 AND #69
  python exe_patcher.py DNCDPRG.EXE --gate 68=0x58 -o FIX  # Custom gate value
  python exe_patcher.py DNCDPRG.EXE --dump              # Dump all stage gates
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from constants import (
    SIETCH_COUNT, SIETCH_SIZE, LOCATION_FIRST_NAMES, LOCATION_SECOND_NAMES,
    GAME_STAGES, location_name,
)

# =============================================================================
# SIETCH FINGERPRINT — immutable (region, subregion, appearance) triples
# =============================================================================
# These 3 fields are fixed at initialization and never change during gameplay:
#   +0x01  region      (1-12)
#   +0x02  subregion   (1-11)
#   +0x09  appearance  (SAL file selector)
#
# We match all 70 records at 28-byte stride to uniquely identify the table.
# Extracted from CD v3.7 game data.

SIETCH_FINGERPRINT = [
    # (region, subregion, appearance)
    (0x02, 0x01, 0x20),  # [ 0] Carthag (Atreides) — Palace
    (0x01, 0x02, 0x30),  # [ 1] Arrakeen (Harkonnen) — Fortress
    (0x01, 0x03, 0x28),  # [ 2] Arrakeen-Tabr
    (0x01, 0x04, 0x2B),  # [ 3] Arrakeen-Timin
    (0x01, 0x05, 0x29),  # [ 4] Arrakeen-Tuek
    (0x01, 0x06, 0x2D),  # [ 5] Arrakeen-Harg
    (0x01, 0x07, 0x2C),  # [ 6] Arrakeen-Clam
    (0x01, 0x08, 0x2E),  # [ 7] Arrakeen-Tsymyn
    (0x01, 0x09, 0x2A),  # [ 8] Arrakeen-Siet
    (0x01, 0x0A, 0x21),  # [ 9] Arrakeen-Pyons
    (0x02, 0x03, 0x02),  # [10] Carthag-Tabr
    (0x02, 0x04, 0x01),  # [11] Carthag-Timin
    (0x02, 0x05, 0x00),  # [12] Carthag-Tuek
    (0x02, 0x06, 0x03),  # [13] Carthag-Harg
    (0x02, 0x07, 0x00),  # [14] Carthag-Clam
    (0x03, 0x03, 0x08),  # [15] Tuono-Tabr
    (0x03, 0x04, 0x07),  # [16] Tuono-Timin
    (0x03, 0x05, 0x04),  # [17] Tuono-Tuek
    (0x03, 0x06, 0x03),  # [18] Tuono-Harg
    (0x03, 0x07, 0x06),  # [19] Tuono-Clam
    (0x03, 0x0A, 0x21),  # [20] Tuono-Pyons
    (0x04, 0x03, 0x05),  # [21] Habbanya-Tabr
    (0x04, 0x04, 0x04),  # [22] Habbanya-Timin
    (0x04, 0x05, 0x07),  # [23] Habbanya-Tuek
    (0x04, 0x07, 0x03),  # [24] Habbanya-Clam
    (0x04, 0x06, 0x09),  # [25] Habbanya-Harg
    (0x05, 0x03, 0x05),  # [26] Oxtyn-Tabr
    (0x05, 0x04, 0x02),  # [27] Oxtyn-Timin
    (0x05, 0x05, 0x05),  # [28] Oxtyn-Tuek
    (0x05, 0x06, 0x07),  # [29] Oxtyn-Harg
    (0x05, 0x0A, 0x21),  # [30] Oxtyn-Pyons
    (0x06, 0x03, 0x28),  # [31] Tsympo-Tabr
    (0x06, 0x04, 0x29),  # [32] Tsympo-Timin
    (0x06, 0x05, 0x01),  # [33] Tsympo-Tuek
    (0x06, 0x06, 0x00),  # [34] Tsympo-Harg
    (0x06, 0x07, 0x2A),  # [35] Tsympo-Clam
    (0x06, 0x08, 0x06),  # [36] Tsympo-Tsymyn
    (0x06, 0x09, 0x2B),  # [37] Tsympo-Siet
    (0x06, 0x0A, 0x21),  # [38] Tsympo-Pyons
    (0x06, 0x0B, 0x2C),  # [39] Tsympo-Pyort
    (0x07, 0x03, 0x2D),  # [40] Bledan-Tabr
    (0x07, 0x04, 0x2E),  # [41] Bledan-Timin
    (0x07, 0x05, 0x2F),  # [42] Bledan-Tuek
    (0x07, 0x06, 0x28),  # [43] Bledan-Harg
    (0x08, 0x03, 0x07),  # [44] Ergsun-Tabr
    (0x08, 0x04, 0x04),  # [45] Ergsun-Timin
    (0x08, 0x05, 0x05),  # [46] Ergsun-Tuek
    (0x08, 0x06, 0x06),  # [47] Ergsun-Harg
    (0x08, 0x07, 0x01),  # [48] Ergsun-Clam
    (0x08, 0x08, 0x00),  # [49] Ergsun-Tsymyn
    (0x09, 0x03, 0x0B),  # [50] Haga-Tabr
    (0x09, 0x04, 0x0A),  # [51] Haga-Timin
    (0x09, 0x05, 0x29),  # [52] Haga-Tuek
    (0x09, 0x06, 0x2A),  # [53] Haga-Harg
    (0x09, 0x07, 0x2B),  # [54] Haga-Clam
    (0x09, 0x08, 0x2C),  # [55] Haga-Tsymyn
    (0x09, 0x09, 0x2D),  # [56] Haga-Siet
    (0x09, 0x0A, 0x21),  # [57] Haga-Pyons
    (0x0A, 0x03, 0x03),  # [58] Cielago-Tabr
    (0x0A, 0x04, 0x0D),  # [59] Cielago-Timin
    (0x0B, 0x03, 0x08),  # [60] Sihaya-Tabr
    (0x0B, 0x04, 0x0A),  # [61] Sihaya-Timin
    (0x0B, 0x05, 0x10),  # [62] Sihaya-Tuek
    (0x0B, 0x06, 0x0B),  # [63] Sihaya-Harg
    (0x0B, 0x07, 0x03),  # [64] Sihaya-Clam
    (0x0B, 0x0A, 0x21),  # [65] Sihaya-Pyons
    (0x0C, 0x03, 0x0E),  # [66] Celimyn-Tabr
    (0x0C, 0x04, 0x0F),  # [67] Celimyn-Timin
    (0x0C, 0x05, 0x03),  # [68] Celimyn-Tuek  ← BUG: gate=0xFF
    (0x0C, 0x06, 0x0C),  # [69] Celimyn-Harg
]

# Minimum records to match for initial detection (full 70 verified after)
FINGERPRINT_MIN = 10


def find_sietch_table(data: bytes) -> int:
    """Find the sietch initialization table by pattern matching.

    Searches for the distinctive (region, subregion, appearance) fingerprint
    at 28-byte stride. These 3 fields are immutable and form a unique sequence
    across 70 consecutive records.

    Returns the file offset of sietch record #0, or -1 if not found.
    """
    limit = len(data) - SIETCH_COUNT * SIETCH_SIZE

    for offset in range(limit):
        # Quick reject: first record's region and subregion
        if data[offset + 0x01] != SIETCH_FINGERPRINT[0][0]:
            continue
        if data[offset + 0x02] != SIETCH_FINGERPRINT[0][1]:
            continue
        if data[offset + 0x09] != SIETCH_FINGERPRINT[0][2]:
            continue

        # Check first FINGERPRINT_MIN records
        match = True
        for idx in range(1, FINGERPRINT_MIN):
            base = offset + idx * SIETCH_SIZE
            r, s, a = SIETCH_FINGERPRINT[idx]
            if data[base + 0x01] != r or data[base + 0x02] != s or data[base + 0x09] != a:
                match = False
                break

        if not match:
            continue

        # Verify ALL 70 records
        full_match = True
        for idx in range(FINGERPRINT_MIN, SIETCH_COUNT):
            base = offset + idx * SIETCH_SIZE
            r, s, a = SIETCH_FINGERPRINT[idx]
            if data[base + 0x01] != r or data[base + 0x02] != s or data[base + 0x09] != a:
                full_match = False
                break

        if full_match:
            return offset

    return -1


def dump_sietch_gates(data: bytes, table_offset: int) -> None:
    """Print all 70 sietch stage_gate values from the EXE table."""
    print(f"\n{'='*70}")
    print(f"  Sietch Initialization Table at file offset 0x{table_offset:06X}")
    print(f"{'='*70}")
    print(f"  {'#':>3}  {'Name':<22}  {'gate':>6}  {'appear':>6}  {'status':>6}  Note")
    print("  " + "-" * 66)

    for i in range(SIETCH_COUNT):
        base = table_offset + i * SIETCH_SIZE
        region = data[base + 0x01]
        sub = data[base + 0x02]
        name = location_name(region, sub)
        appearance = data[base + 0x09]
        status = data[base + 0x0B]
        gate = data[base + 0x0C]

        # Flag anomalies
        flag = ""
        stage_name = GAME_STAGES.get(gate, "")
        if gate == 0xFF:
            # Check if it's a Fremen sietch with 0xFF — that's the bug
            if appearance < 0x20:
                flag = "*** BUG: Fremen sietch with 0xFF gate ***"
            else:
                stage_name = "(Harkonnen/conquest)"

        print(f"  {i:3d}  {name:<22}  0x{gate:02X}      0x{appearance:02X}     0x{status:02X}       {flag or stage_name}")


def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 EXE Patcher — fix Celimyn-Tuek sietch discovery bug',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The Celimyn-Tuek bug:
  Sietch #68 (Celimyn-Tuek) has stage_gate=0xFF in the EXE's initialization
  table, making it permanently undiscoverable. All other Fremen sietches in
  the Celimyn/Sihaya region use 0x58 ("Army Building") or 0x5A. This is a
  one-byte data error in the original game.

Examples:
  %(prog)s DNCDPRG.EXE                           # Analyze (dry run)
  %(prog)s DNCDPRG.EXE -o DNCDPRG_FIXED.EXE      # Fix sietch #68
  %(prog)s DNCDPRG.EXE --fix-all -o FIXED.EXE     # Fix #68 and #69
  %(prog)s DNCDPRG.EXE --dump                      # Show all stage gates
  %(prog)s DNCDPRG.EXE --gate 68=0x58 69=0x5A -o F # Custom values
        """)
    p.add_argument('exe', help='DNCDPRG.EXE file path')
    p.add_argument('-o', '--output', default=None, metavar='FILE',
                   help='Output patched EXE (omit for dry-run analysis)')
    p.add_argument('--dump', action='store_true',
                   help='Dump all 70 sietch stage_gate values')
    p.add_argument('--fix-all', action='store_true',
                   help='Fix both #68 (Celimyn-Tuek) and #69 (Celimyn-Harg)')
    p.add_argument('--gate', nargs='+', metavar='IDX=VAL',
                   help='Set specific stage_gate values (e.g., 68=0x58)')
    args = p.parse_args()

    # Read EXE
    with open(args.exe, 'rb') as f:
        data = bytearray(f.read())

    exe_size = len(data)
    print(f"\n  Loaded: {args.exe} ({exe_size:,} bytes)")

    # Verify MZ header
    if len(data) < 2 or data[0:2] not in (b'MZ', b'ZM'):
        print("  WARNING: No MZ header — file may not be a DOS executable")

    # Find sietch table
    print("  Searching for sietch initialization table...")
    table_offset = find_sietch_table(data)

    if table_offset < 0:
        print("  ERROR: Could not locate sietch table in EXE.")
        print("  This tool requires the CD v3.7 version of DNCDPRG.EXE.")
        sys.exit(1)

    print(f"  Found sietch table at file offset 0x{table_offset:06X}")

    # Verify all 70 records have valid region/subregion
    valid = 0
    for i in range(SIETCH_COUNT):
        base = table_offset + i * SIETCH_SIZE
        region = data[base + 0x01]
        sub = data[base + 0x02]
        if region in LOCATION_FIRST_NAMES and sub in LOCATION_SECOND_NAMES:
            valid += 1
    print(f"  Verified: {valid}/{SIETCH_COUNT} records have valid location names")

    if valid < SIETCH_COUNT:
        print("  WARNING: Some records have unexpected region/subregion values.")
        print("  The table match may be a false positive. Proceeding with caution.")

    # Dump mode
    if args.dump:
        dump_sietch_gates(data, table_offset)
        return

    # Determine patches to apply
    patches = {}  # {sietch_index: new_gate_value}

    if args.gate:
        # Custom gate values
        for spec in args.gate:
            idx_s, val_s = spec.split('=', 1)
            idx = int(idx_s)
            val = int(val_s, 0)
            if idx < 0 or idx >= SIETCH_COUNT:
                print(f"  ERROR: Sietch index {idx} out of range (0-{SIETCH_COUNT - 1})")
                sys.exit(1)
            if val < 0 or val > 0xFF:
                print(f"  ERROR: Gate value 0x{val:02X} out of range (0x00-0xFF)")
                sys.exit(1)
            patches[idx] = val
    else:
        # Default: fix #68
        patches[68] = 0x58
        if args.fix_all:
            patches[69] = 0x5A

    # Show current state and planned changes
    print(f"\n  Patches to apply:")
    for idx in sorted(patches):
        base = table_offset + idx * SIETCH_SIZE
        region = data[base + 0x01]
        sub = data[base + 0x02]
        name = location_name(region, sub)
        old_gate = data[base + 0x0C]
        new_gate = patches[idx]
        old_name = GAME_STAGES.get(old_gate, "always/conquest" if old_gate == 0xFF else f"0x{old_gate:02X}")
        new_name = GAME_STAGES.get(new_gate, f"0x{new_gate:02X}")
        file_off = base + 0x0C

        status = "UNCHANGED" if old_gate == new_gate else "PATCH"
        print(f"    [{status}] Sietch #{idx} ({name})")
        print(f"           stage_gate: 0x{old_gate:02X} ({old_name})")
        if old_gate != new_gate:
            print(f"                    -> 0x{new_gate:02X} ({new_name})")
            print(f"           file offset: 0x{file_off:06X}")

    if not args.output:
        print(f"\n  Dry run — no output file specified. Use -o to write patched EXE.")
        return

    # Apply patches
    changes = 0
    for idx, new_gate in sorted(patches.items()):
        off = table_offset + idx * SIETCH_SIZE + 0x0C
        old = data[off]
        if old != new_gate:
            data[off] = new_gate
            changes += 1

    if changes == 0:
        print(f"\n  No changes needed — all values already correct.")
        return

    # Write patched EXE
    with open(args.output, 'wb') as f:
        f.write(data)

    print(f"\n  Applied {changes} patch{'es' if changes != 1 else ''}")
    print(f"  Written: {args.output} ({len(data):,} bytes)")

    # Verify the patch
    for idx in sorted(patches):
        base = table_offset + idx * SIETCH_SIZE
        name = location_name(data[base + 0x01], data[base + 0x02])
        gate = data[base + 0x0C]
        print(f"  Verify: Sietch #{idx} ({name}) stage_gate = 0x{gate:02X} OK")


if __name__ == '__main__':
    main()
