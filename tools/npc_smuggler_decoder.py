#!/usr/bin/env python
"""
Dune 1992 NPC & Smuggler Save Data Decoder
=============================================
Extract and display NPC and Smuggler data from DUNE*.SAV save files.

NPC data block (save offset 0x53F4):
  16 NPCs × 16 bytes (8 data + 8 padding)
  Fields: SpriteId, FieldB, RoomLocation, TypeOfPlace,
          DialogueAvailable, ExactPlace, ForDialogue, FieldH

Smuggler data block (save offset 0x54F6):
  6 Smugglers × 17 bytes (14 data + 3 padding)
  Fields: Region, WillingnessToHaggle, FieldC, FieldD,
          Harvesters, Ornithopters, KrysKnives, LaserGuns, WeirdingModules,
          HarvestersPrice, OrnithoptersPrice, KrysKnivesPrice,
          LaserGunsPrice, WeirdingModulesPrice

Usage:
  python npc_smuggler_decoder.py DUNE37S1.SAV           # Show all NPCs + Smugglers
  python npc_smuggler_decoder.py DUNE37S1.SAV --npcs    # NPCs only
  python npc_smuggler_decoder.py DUNE37S1.SAV --smugglers  # Smugglers only
  python npc_smuggler_decoder.py DUNE37S1.SAV --npc 5   # Single NPC by index
  python npc_smuggler_decoder.py DUNE37S1.SAV --raw     # Include hex dump
"""

import struct
import sys
import argparse
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.compression import f7_decompress
from lib.constants import (
    SAVE_OFFSETS, NPC_COUNT, NPC_STRIDE, NPC_SIZE,
    NPC_FIELDS, NPC_SPRITES,
    SMUGGLER_COUNT, SMUGGLER_STRIDE, SMUGGLER_SIZE,
    SMUGGLER_FIELDS,
)


# =============================================================================
# SAVE FILE LOADER
# =============================================================================

def load_save(path: str) -> bytes:
    """Load and decompress a DUNE*.SAV file."""
    with open(path, 'rb') as f:
        raw = f.read()
    return bytes(f7_decompress(raw))


# =============================================================================
# NPC DECODER
# =============================================================================

def decode_npc(data: bytes, index: int) -> dict:
    """Decode a single NPC record from save data."""
    base = SAVE_OFFSETS["npc_data"] + index * NPC_STRIDE
    record = data[base:base + NPC_SIZE]

    npc = {"index": index, "offset": base}
    for field_off, (name, _type, _desc) in NPC_FIELDS.items():
        npc[name] = record[field_off] if field_off < len(record) else 0

    # Resolve character name from FieldB (character index)
    # SpriteId (byte 0) is always 0x00 in saves — runtime-initialized
    # FieldB (byte 1) is the actual character ID matching NPC_SPRITES
    char_id = npc.get("FieldB", 0)
    npc["CharacterName"] = NPC_SPRITES.get(char_id, f"Unknown(0x{char_id:02X})")

    # Raw bytes for hex display
    npc["raw"] = record
    npc["padding"] = data[base + NPC_SIZE:base + NPC_STRIDE]

    return npc


def decode_all_npcs(data: bytes) -> list:
    """Decode all 16 NPC records."""
    return [decode_npc(data, i) for i in range(NPC_COUNT)]


# =============================================================================
# SMUGGLER DECODER
# =============================================================================

def decode_smuggler(data: bytes, index: int) -> dict:
    """Decode a single Smuggler record from save data."""
    base = SAVE_OFFSETS["smuggler_data"] + index * SMUGGLER_STRIDE
    record = data[base:base + SMUGGLER_SIZE]

    smug = {"index": index, "offset": base}
    for field_off, (name, _type, _desc) in SMUGGLER_FIELDS.items():
        smug[name] = record[field_off] if field_off < len(record) else 0

    smug["raw"] = record
    smug["padding"] = data[base + SMUGGLER_SIZE:base + SMUGGLER_STRIDE]

    return smug


def decode_all_smugglers(data: bytes) -> list:
    """Decode all 6 Smuggler records."""
    return [decode_smuggler(data, i) for i in range(SMUGGLER_COUNT)]


# =============================================================================
# DISPLAY
# =============================================================================

def show_npc_summary(npc: dict, show_raw: bool = False):
    """Display a single NPC in summary format."""
    char_id = npc["FieldB"]
    name = npc["CharacterName"]
    room = npc["RoomLocation"]
    place_type = npc["TypeOfPlace"]
    dlg_avail = npc["DialogueAvailable"]
    exact = npc["ExactPlace"]
    for_dlg = npc["ForDialogue"]

    # Compact display
    name_padded = name[:28].ljust(28)
    line = (f"NPC[{npc['index']:2d}] "
            f"CharId=0x{char_id:02X} ({name_padded}) "
            f"Room=0x{room:02X} Type=0x{place_type:02X} "
            f"DlgAvail=0x{dlg_avail:02X} Exact=0x{exact:02X} "
            f"ForDlg=0x{for_dlg:02X}")
    print(line)

    if show_raw:
        raw_hex = ' '.join(f'{b:02X}' for b in npc["raw"])
        pad_hex = ' '.join(f'{b:02X}' for b in npc["padding"])
        print(f"         Data: {raw_hex}  Pad: {pad_hex}")


def show_npc_detail(npc: dict):
    """Display a single NPC in detailed format."""
    print(f"=== NPC [{npc['index']}] @ offset 0x{npc['offset']:04X} ===")
    print(f"  Character: {npc['CharacterName']}")
    for field_off, (name, _type, desc) in NPC_FIELDS.items():
        val = npc[name]
        print(f"  {name:22s} = 0x{val:02X} ({val:3d})  — {desc}")
    raw_hex = ' '.join(f'{b:02X}' for b in npc["raw"])
    print(f"  Raw bytes: {raw_hex}")


def show_smuggler_summary(smug: dict, show_raw: bool = False):
    """Display a single Smuggler in summary format."""
    region = smug["Region"]
    haggle = smug["WillingnessToHaggle"]

    # Inventory
    inv_parts = []
    for item in ("Harvesters", "Ornithopters", "KrysKnives", "LaserGuns", "WeirdingModules"):
        qty = smug[item]
        price = smug[item + "Price"]
        if qty > 0:
            inv_parts.append(f"{item}={qty}@{price}")

    inv_str = ', '.join(inv_parts) if inv_parts else "Empty"

    print(f"SMUG[{smug['index']}] "
          f"Region=0x{region:02X} Haggle={haggle:3d} "
          f"Stock: {inv_str}")

    if show_raw:
        raw_hex = ' '.join(f'{b:02X}' for b in smug["raw"])
        print(f"        Data: {raw_hex}")


def show_smuggler_detail(smug: dict):
    """Display a single Smuggler in detailed format."""
    print(f"=== Smuggler [{smug['index']}] @ offset 0x{smug['offset']:04X} ===")
    for field_off, (name, _type, desc) in SMUGGLER_FIELDS.items():
        val = smug[name]
        print(f"  {name:22s} = 0x{val:02X} ({val:3d})  — {desc}")
    raw_hex = ' '.join(f'{b:02X}' for b in smug["raw"])
    print(f"  Raw bytes: {raw_hex}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 NPC & Smuggler Save Data Decoder',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('file', help='DUNE*.SAV save file')
    p.add_argument('--npcs', action='store_true',
                   help='Show NPCs only')
    p.add_argument('--smugglers', action='store_true',
                   help='Show Smugglers only')
    p.add_argument('--npc', type=int, default=None, metavar='N',
                   help='Show single NPC by index (0-15)')
    p.add_argument('--smuggler', type=int, default=None, metavar='N',
                   help='Show single Smuggler by index (0-5)')
    p.add_argument('--raw', action='store_true',
                   help='Include raw hex dump')
    args = p.parse_args()

    data = load_save(args.file)
    print(f"  Loaded: {len(data):,} bytes decompressed\n")

    show_all = not args.npcs and not args.smugglers and args.npc is None and args.smuggler is None

    # Single NPC detail
    if args.npc is not None:
        if 0 <= args.npc < NPC_COUNT:
            npc = decode_npc(data, args.npc)
            show_npc_detail(npc)
        else:
            print(f"NPC index {args.npc} out of range (0-{NPC_COUNT - 1})")
        return

    # Single Smuggler detail
    if args.smuggler is not None:
        if 0 <= args.smuggler < SMUGGLER_COUNT:
            smug = decode_smuggler(data, args.smuggler)
            show_smuggler_detail(smug)
        else:
            print(f"Smuggler index {args.smuggler} out of range (0-{SMUGGLER_COUNT - 1})")
        return

    # NPCs
    if show_all or args.npcs:
        npcs = decode_all_npcs(data)
        active = [n for n in npcs if n["FieldB"] != 0xFF]
        print(f"=== NPCs ({len(active)} active / {NPC_COUNT} total) ===")
        print(f"    Save offset: 0x{SAVE_OFFSETS['npc_data']:04X}, "
              f"{NPC_COUNT} × {NPC_STRIDE} bytes\n")
        for npc in npcs:
            if npc["FieldB"] != 0xFF or args.raw:
                show_npc_summary(npc, args.raw)
        print()

    # Smugglers
    if show_all or args.smugglers:
        smugglers = decode_all_smugglers(data)
        active = [s for s in smugglers if s["Region"] != 0]
        print(f"=== Smugglers ({len(active)} active / {SMUGGLER_COUNT} total) ===")
        print(f"    Save offset: 0x{SAVE_OFFSETS['smuggler_data']:04X}, "
              f"{SMUGGLER_COUNT} × {SMUGGLER_STRIDE} bytes\n")
        for smug in smugglers:
            show_smuggler_summary(smug, args.raw)
        print()


if __name__ == '__main__':
    main()
