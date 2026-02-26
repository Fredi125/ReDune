#!/usr/bin/env python
"""
Dune 1992 Save File Editor
===========================
Read and modify Dune (1992 CD v3.7) save game files.

Handles F7 RLE compression/decompression transparently.
Supports editing globals, troops, and sietches.

Usage:
  python save_editor.py DUNE37S1.SAV                  # Show summary
  python save_editor.py DUNE37S1.SAV --globals         # Show global variables
  python save_editor.py DUNE37S1.SAV --troops          # List all troops
  python save_editor.py DUNE37S1.SAV --troop 5         # Show troop #5 detail
  python save_editor.py DUNE37S1.SAV --sietches        # List all sietches
  python save_editor.py DUNE37S1.SAV --sietch 3        # Show sietch #3 detail
  python save_editor.py DUNE37S1.SAV --set stage=0x50  # Set GameStage
  python save_editor.py DUNE37S1.SAV --set spice=9999  # Set spice (raw value; ×10 = kg)
  python save_editor.py DUNE37S1.SAV --set charisma=255
  python save_editor.py DUNE37S1.SAV --set day=100 --set hour=8
  python save_editor.py DUNE37S1.SAV --set-troop 5 job=4 equip=0xFF
  python save_editor.py DUNE37S1.SAV --set-sietch 3 water=255 spice=255
  python save_editor.py DUNE37S1.SAV -o modified.SAV   # Write to new file
"""

import struct
import sys
import argparse
import os

# Add parent dir to path for lib imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.compression import f7_decompress, f7_compress
from lib.constants import (
    SAVE_OFFSETS as OFF, SIETCH_COUNT, SIETCH_SIZE, TROOP_COUNT, TROOP_SIZE,
    GAME_STAGES, TROOP_JOBS, equipment_str,
)


class DuneSave:
    """Represents a decompressed Dune 1992 save file."""

    def __init__(self, path):
        with open(path, 'rb') as f:
            raw = f.read()
        self.path = path
        self.data = f7_decompress(raw)
        self._compressed_size = len(raw)
        print(f"  Loaded: {len(raw)} bytes compressed → {len(self.data)} bytes decompressed")

    def u8(self, off):  return self.data[off]
    def u16(self, off): return struct.unpack_from('<H', self.data, off)[0]
    def w8(self, off, v):  self.data[off] = v & 0xFF
    def w16(self, off, v): struct.pack_into('<H', self.data, off, v & 0xFFFF)

    # -- Global properties --

    @property
    def game_stage(self): return self.u8(OFF["game_stage"])
    @game_stage.setter
    def game_stage(self, v): self.w8(OFF["game_stage"], v)

    @property
    def charisma(self): return self.u8(OFF["charisma"])
    @charisma.setter
    def charisma(self, v): self.w8(OFF["charisma"], v)

    @property
    def rallied_troops(self): return self.u8(OFF["rallied_troops"])
    @rallied_troops.setter
    def rallied_troops(self, v): self.w8(OFF["rallied_troops"], v)

    @property
    def spice(self): return self.u16(OFF["spice"])
    @spice.setter
    def spice(self, v): self.w16(OFF["spice"], v)

    @property
    def datetime_raw(self): return self.u16(OFF["datetime"])

    @property
    def hour(self): return self.datetime_raw & 0xF
    @property
    def day(self):  return self.datetime_raw >> 4

    def set_time(self, day=None, hour=None):
        d = day if day is not None else self.day
        h = hour if hour is not None else self.hour
        self.w16(OFF["datetime"], (d << 4) | (h & 0xF))

    @property
    def contact_distance(self): return self.u8(OFF["contact_distance"])
    @contact_distance.setter
    def contact_distance(self, v): self.w8(OFF["contact_distance"], v)

    # -- Troops --

    def troop_offset(self, idx):
        return OFF["troop_block"] + idx * TROOP_SIZE

    def troop(self, idx):
        off = self.troop_offset(idx)
        raw = self.data[off:off + TROOP_SIZE]
        return {
            'index': idx,
            'troop_id': raw[0], 'next_troop': raw[1], 'prev_troop': raw[2],
            'job': raw[3], 'unknown_04': raw[4], 'sietch_id': raw[5],
            'unknown_06': raw[6], 'unknown_07': raw[7],
            'spice_skill': raw[8], 'army_skill': raw[9], 'eco_skill': raw[10],
            'equipment': raw[11],
            'population': struct.unpack_from('<H', raw, 12)[0],
            'motivation': raw[14], 'spice_mining_rate': raw[15],
            'dissatisfaction': raw[25],
        }

    TROOP_FIELDS = {
        'troop_id': (0, 1), 'job': (3, 1), 'sietch_id': (5, 1),
        'spice_skill': (8, 1), 'army_skill': (9, 1), 'eco_skill': (10, 1),
        'equipment': (11, 1), 'equip': (11, 1),
        'population': (12, 2), 'motivation': (14, 1),
        'spice_mining_rate': (15, 1), 'dissatisfaction': (25, 1),
    }

    def set_troop_field(self, idx, field, value):
        if field not in self.TROOP_FIELDS:
            print(f"  Unknown troop field: {field}")
            return False
        foff, fsize = self.TROOP_FIELDS[field]
        off = self.troop_offset(idx) + foff
        if fsize == 1: self.w8(off, value)
        else: self.w16(off, value)
        return True

    # -- Sietches --

    def sietch_offset(self, idx):
        return OFF["sietch_block"] + idx * SIETCH_SIZE

    def sietch(self, idx):
        off = self.sietch_offset(idx)
        raw = self.data[off:off + SIETCH_SIZE]
        status = raw[0]
        return {
            'index': idx, 'status': status,
            'discovered': bool(status & 0x01), 'visited': bool(status & 0x02),
            'vegetation': bool(status & 0x04), 'in_battle': bool(status & 0x08),
            'gps_x': struct.unpack_from('<H', raw, 2)[0],
            'gps_y': struct.unpack_from('<H', raw, 4)[0],
            'region': raw[6], 'housed_troop': raw[7], 'spice_density': raw[8],
            'equipment': raw[25], 'water': raw[26], 'spice': raw[27],
        }

    SIETCH_FIELDS = {
        'status': (0, 1), 'region': (6, 1), 'housed_troop': (7, 1),
        'spice_density': (8, 1), 'equipment': (25, 1), 'equip': (25, 1),
        'water': (26, 1), 'spice': (27, 1),
    }

    def set_sietch_field(self, idx, field, value):
        if field not in self.SIETCH_FIELDS:
            print(f"  Unknown sietch field: {field}")
            return False
        foff, _ = self.SIETCH_FIELDS[field]
        self.w8(self.sietch_offset(idx) + foff, value)
        return True

    # -- I/O --

    def save(self, path):
        compressed = f7_compress(self.data)
        with open(path, 'wb') as f:
            f.write(compressed)
        print(f"  Saved: {len(self.data)} bytes → {len(compressed)} bytes compressed → {path}")


# =============================================================================
# DISPLAY FUNCTIONS
# =============================================================================

def show_globals(sav):
    gs = sav.game_stage
    stage_name = GAME_STAGES.get(gs, "Unknown")
    print(f"\n{'='*60}")
    print(f" DUNE 1992 Save: {sav.path}")
    print(f" {sav._compressed_size:,} bytes compressed → {len(sav.data):,} bytes")
    print(f"{'='*60}\n")
    print(f"  Game Stage:      0x{gs:02X} = {stage_name}")
    print(f"  Date/Time:       Day {sav.day}, Hour {sav.hour} (raw: 0x{sav.datetime_raw:04X})")
    print(f"  Charisma:        {sav.charisma} (displayed: {sav.charisma // 2})")
    print(f"  Rallied Troops:  {sav.rallied_troops}")
    print(f"  Spice Stockpile: {sav.spice} (= {sav.spice * 10:,} kg)")
    print(f"  Contact Dist:    {sav.contact_distance}")


def show_troops(sav, detail_idx=None):
    if detail_idx is not None:
        t = sav.troop(detail_idx)
        print(f"\n=== Troop #{detail_idx} Detail ===")
        print(f"  Troop ID:    {t['troop_id']}")
        print(f"  Job:         {t['job']} = {TROOP_JOBS.get(t['job'], '?')}")
        print(f"  Sietch:      {t['sietch_id']}")
        print(f"  Population:  {t['population']:,}")
        print(f"  Motivation:  {t['motivation']}")
        print(f"  Skills:      Spice={t['spice_skill']}  Army={t['army_skill']}  Eco={t['eco_skill']}")
        print(f"  Equipment:   0x{t['equipment']:02X} = {equipment_str(t['equipment'])}")
        print(f"  Mining Rate: {t['spice_mining_rate']}")
        print(f"  Dissatisf:   {t['dissatisfaction']}")
        off = sav.troop_offset(detail_idx)
        raw = ' '.join(f'{sav.data[off + i]:02X}' for i in range(TROOP_SIZE))
        print(f"  Raw bytes:   {raw}")
        return

    print(f"\n=== Troops ({TROOP_COUNT} records) ===")
    fmt = "{:>3}  {:>3}  {:<20}  {:>6}  {:>6}  {:>5}  {}"
    print(fmt.format("#", "ID", "Job", "Sietch", "Pop", "Motiv", "Equipment"))
    print(fmt.format("---", "---", "---", "---", "---", "---", "---"))
    for i in range(TROOP_COUNT):
        t = sav.troop(i)
        if t['troop_id'] == 0 and t['population'] == 0:
            continue
        job = TROOP_JOBS.get(t['job'], f"?{t['job']}")
        eq = equipment_str(t['equipment'])
        print(fmt.format(i, t['troop_id'], job, t['sietch_id'], t['population'], t['motivation'], eq))


def show_sietches(sav, detail_idx=None):
    if detail_idx is not None:
        s = sav.sietch(detail_idx)
        flags = []
        if s['discovered']: flags.append('DISCOVERED')
        if s['visited']:    flags.append('VISITED')
        if s['vegetation']: flags.append('VEGETATION')
        if s['in_battle']:  flags.append('IN_BATTLE')
        print(f"\n=== Sietch #{detail_idx} Detail ===")
        print(f"  Status:      0x{s['status']:02X} = {', '.join(flags) or 'None'}")
        print(f"  GPS:         ({s['gps_x']}, {s['gps_y']})")
        print(f"  Region:      {s['region']}")
        print(f"  Troop:       {s['housed_troop']}")
        print(f"  Spice Dens:  {s['spice_density']}")
        print(f"  Equipment:   0x{s['equipment']:02X} = {equipment_str(s['equipment'])}")
        print(f"  Water:       {s['water']}")
        print(f"  Spice:       {s['spice']}")
        off = sav.sietch_offset(detail_idx)
        raw = ' '.join(f'{sav.data[off + i]:02X}' for i in range(SIETCH_SIZE))
        print(f"  Raw bytes:   {raw}")
        return

    print(f"\n=== Sietches ({SIETCH_COUNT} records) ===")
    fmt = "{:>3}  {:<8}  {:>12}  {:>3}  {:>3}  {:<20}  {:>3}  {:>3}"
    print(fmt.format("#", "Status", "GPS", "Rgn", "Trp", "Equipment", "Wtr", "Spc"))
    for i in range(SIETCH_COUNT):
        s = sav.sietch(i)
        if s['status'] == 0 and s['gps_x'] == 0 and s['gps_y'] == 0:
            continue
        flags = []
        if s['discovered']: flags.append('D')
        if s['visited']:    flags.append('V')
        if s['vegetation']: flags.append('E')
        if s['in_battle']:  flags.append('B')
        status = '|'.join(flags) or '-'
        gps = f"({s['gps_x']},{s['gps_y']})"
        eq = equipment_str(s['equipment'])[:20]
        print(fmt.format(i, status, gps, s['region'], s['housed_troop'], eq, s['water'], s['spice']))


# =============================================================================
# MAIN
# =============================================================================

def parse_value(s):
    """Parse int from string (supports 0x hex prefix)."""
    s = s.strip()
    if s.startswith(('0x', '0X')):
        return int(s, 16)
    return int(s)


def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 Save File Editor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s DUNE37S1.SAV --globals
  %(prog)s DUNE37S1.SAV --troops
  %(prog)s DUNE37S1.SAV --set stage=0x50 --set spice=9999 -o modified.SAV
  %(prog)s DUNE37S1.SAV --set-troop 5 job=4 equip=0xFF
  %(prog)s DUNE37S1.SAV --hex 0x4448
        """)
    p.add_argument('file', help='Save file path (e.g. DUNE37S1.SAV)')
    p.add_argument('--globals', action='store_true', help='Show global variables')
    p.add_argument('--troops', action='store_true', help='List all troops')
    p.add_argument('--troop', type=int, default=None, metavar='N', help='Show troop N detail')
    p.add_argument('--sietches', action='store_true', help='List all sietches')
    p.add_argument('--sietch', type=int, default=None, metavar='N', help='Show sietch N detail')
    p.add_argument('--set', action='append', default=[], metavar='KEY=VAL',
                   help='Set global: stage, spice, charisma, rallied, day, hour, contact')
    p.add_argument('--set-troop', nargs='+', metavar='ARG',
                   help='N KEY=VAL [KEY=VAL ...]: Set troop fields')
    p.add_argument('--set-sietch', nargs='+', metavar='ARG',
                   help='N KEY=VAL [KEY=VAL ...]: Set sietch fields')
    p.add_argument('-o', '--output', default=None, metavar='FILE',
                   help='Output file (default: overwrite input)')
    p.add_argument('--hex', type=lambda x: int(x, 0), default=None, metavar='OFFSET',
                   help='Hex dump 64 bytes at offset')
    args = p.parse_args()

    sav = DuneSave(args.file)
    modified = False

    # Apply global edits
    for kv in args.set:
        k, v = kv.split('=', 1)
        val = parse_value(v)
        k = k.lower()
        setters = {
            'stage':    lambda v: (setattr(sav, 'game_stage', v), f"GameStage = 0x{v:02X} ({GAME_STAGES.get(v, '?')})"),
            'spice':    lambda v: (setattr(sav, 'spice', v), f"Spice = {v} ({v*10:,} kg)"),
            'charisma': lambda v: (setattr(sav, 'charisma', v), f"Charisma = {v} (display: {v//2})"),
            'rallied':  lambda v: (setattr(sav, 'rallied_troops', v), f"RalliedTroops = {v}"),
            'day':      lambda v: (sav.set_time(day=v), f"Day = {v}"),
            'hour':     lambda v: (sav.set_time(hour=v), f"Hour = {v}"),
            'contact':  lambda v: (setattr(sav, 'contact_distance', v), f"ContactDistance = {v}"),
        }
        if k in setters:
            _, msg = setters[k](val)
            print(f"  Set {msg}")
            modified = True
        else:
            print(f"  Unknown key: {k}")

    # Apply troop edits
    if args.set_troop:
        idx = int(args.set_troop[0])
        for kv in args.set_troop[1:]:
            k, v = kv.split('=', 1)
            if sav.set_troop_field(idx, k.lower(), parse_value(v)):
                modified = True
                print(f"  Set Troop[{idx}].{k} = {parse_value(v)}")

    # Apply sietch edits
    if args.set_sietch:
        idx = int(args.set_sietch[0])
        for kv in args.set_sietch[1:]:
            k, v = kv.split('=', 1)
            if sav.set_sietch_field(idx, k.lower(), parse_value(v)):
                modified = True
                print(f"  Set Sietch[{idx}].{k} = {parse_value(v)}")

    # Save if modified
    if modified:
        sav.save(args.output or args.file)

    # Display modes
    if args.hex is not None:
        off = args.hex
        chunk = sav.data[off:off + 64]
        print(f"\nHex dump at 0x{off:04X}:")
        for i in range(0, len(chunk), 16):
            hex_str = ' '.join(f'{b:02X}' for b in chunk[i:i + 16])
            asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk[i:i + 16])
            print(f"  {off + i:04X}: {hex_str:<48}  {asc}")
        return

    if args.troop is not None:   return show_troops(sav, args.troop)
    if args.sietch is not None:  return show_sietches(sav, args.sietch)
    if args.troops:              return show_troops(sav)
    if args.sietches:            return show_sietches(sav)
    if args.globals:
        show_globals(sav)
        return

    # Default: summary
    show_globals(sav)
    print()
    active = sum(1 for i in range(TROOP_COUNT) if sav.troop(i)['population'] > 0)
    discovered = sum(1 for i in range(SIETCH_COUNT) if sav.sietch(i)['discovered'])
    print(f"  Active Troops:       {active} / {TROOP_COUNT}")
    print(f"  Discovered Sietches: {discovered} / {SIETCH_COUNT}")
    print(f"\n  Use --troops, --sietches, --globals for details.")
    print(f"  Use --set KEY=VAL to edit, -o FILE to save to new file.")


if __name__ == '__main__':
    main()
