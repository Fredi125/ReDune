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
    location_name, sietch_status_str, SIETCH_STATUS_FLAGS,
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
        """Parse sietch record (28 bytes) using corrected byte layout.

        Layout (0-indexed, CD v3.7):
          +0x00  byte0       Unknown (mostly 0x00; purpose TBD)
          +0x01  region      First name code (1-12, COMMAND[region-1])
          +0x02  subregion   Second name code (1-11, COMMAND[sub+11])
          +0x03  coord1      GPS/coordinate byte 1
          +0x04  coord2      GPS/coordinate byte 2
          +0x05  coord3      GPS/coordinate byte 3 (with +0x06 forms int16)
          +0x06  coord_sign  Coordinate sign/hemisphere (0x00 or 0xFF only)
          +0x07  pos_x       Screen/sprite position X
          +0x08  pos_y       Screen/sprite position Y
          +0x09  appearance  Type / interior appearance code
          +0x0A  troop_id    Housed troop ID (0-67)
          +0x0B  status      Status bitfield (flags below)
          +0x0C  stage_gate  GameStage discovery threshold (0xFF=always)
          +0x0D  unk3        Reserved (always 0 in observed saves)
          +0x0E  unk4        Reserved
          +0x0F  unk5        Reserved
          +0x10  unk6        Reserved
          +0x11  spice_fld   Spice field ID (1-76, unique per sietch)
          +0x12  spice_amt   Spice amount (stockpile at sietch)
          +0x13  spice_dens  Spice density (mining yield, 0-250)
          +0x14  unk8        Unknown (possibly ecology/battle counter)
          +0x15  harvesters  Harvester count
          +0x16  ornithopters Ornithopter count
          +0x17  knives      Knife count
          +0x18  guns        Laser gun count
          +0x19  weirding    Weirding module count
          +0x1A  atomics     Atomics count
          +0x1B  bulbs       Bulb count (or water; all 0 in observed saves)

        Status bits (+0x0B):
          0x01  Vegetation     0x10  Inventory visible
          0x02  In battle      0x20  Wind-trap built
                               0x40  Prospected
                               0x80  Undiscovered
        """
        off = self.sietch_offset(idx)
        raw = self.data[off:off + SIETCH_SIZE]
        status = raw[0x0B]
        return {
            'index': idx,
            'byte0': raw[0x00],
            'region': raw[0x01],
            'subregion': raw[0x02],
            'name': location_name(raw[0x01], raw[0x02]),
            'coord1': raw[0x03],
            'coord2': raw[0x04],
            'coord3': raw[0x05],
            'coord_sign': raw[0x06],
            'pos_x': raw[0x07],
            'pos_y': raw[0x08],
            'appearance': raw[0x09],
            'troop_id': raw[0x0A],
            'status': status,
            'discovered': not bool(status & 0x80),
            'prospected': bool(status & 0x40),
            'windtrap': bool(status & 0x20),
            'inventory': bool(status & 0x10),
            'in_battle': bool(status & 0x02),
            'vegetation': bool(status & 0x01),
            'stage_gate': raw[0x0C],
            'spice_field': raw[0x11],
            'spice_amount': raw[0x12],
            'spice_density': raw[0x13],
            'harvesters': raw[0x15],
            'ornithopters': raw[0x16],
            'knives': raw[0x17],
            'guns': raw[0x18],
            'weirding': raw[0x19],
            'atomics': raw[0x1A],
            'bulbs': raw[0x1B],
        }

    SIETCH_FIELDS = {
        'byte0': (0x00, 1),
        'region': (0x01, 1), 'subregion': (0x02, 1),
        'appearance': (0x09, 1), 'troop_id': (0x0A, 1), 'troop': (0x0A, 1),
        'status': (0x0B, 1), 'stage_gate': (0x0C, 1),
        'spice_field': (0x11, 1), 'spice_amount': (0x12, 1), 'spice': (0x12, 1),
        'spice_density': (0x13, 1),
        'harvesters': (0x15, 1), 'ornithopters': (0x16, 1),
        'knives': (0x17, 1), 'guns': (0x18, 1),
        'weirding': (0x19, 1), 'atomics': (0x1A, 1), 'bulbs': (0x1B, 1),
    }

    def set_sietch_field(self, idx, field, value):
        if field not in self.SIETCH_FIELDS:
            print(f"  Unknown sietch field: {field}")
            print(f"  Available: {', '.join(sorted(self.SIETCH_FIELDS.keys()))}")
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


def _equip_summary(s):
    """One-line equipment summary from individual sietch counts."""
    parts = []
    if s['harvesters']:  parts.append(f"H:{s['harvesters']}")
    if s['ornithopters']:parts.append(f"O:{s['ornithopters']}")
    if s['knives']:      parts.append(f"K:{s['knives']}")
    if s['guns']:        parts.append(f"G:{s['guns']}")
    if s['weirding']:    parts.append(f"W:{s['weirding']}")
    if s['atomics']:     parts.append(f"A:{s['atomics']}")
    if s['bulbs']:       parts.append(f"B:{s['bulbs']}")
    return ' '.join(parts) if parts else '-'


def show_sietches(sav, detail_idx=None):
    if detail_idx is not None:
        s = sav.sietch(detail_idx)
        status_desc = sietch_status_str(s['status'])
        print(f"\n=== Sietch #{detail_idx}: {s['name']} ===")
        print(f"  Region:       {s['region']} / Subregion: {s['subregion']}")
        print(f"  Status:       0x{s['status']:02X} = {status_desc}")
        print(f"  Discovered:   {'Yes' if s['discovered'] else 'No'}")
        if s['prospected']:  print(f"  Prospected:   Yes")
        if s['windtrap']:    print(f"  Wind-trap:    Yes")
        if s['inventory']:   print(f"  Inventory:    Visible")
        if s['vegetation']:  print(f"  Vegetation:   Yes")
        if s['in_battle']:   print(f"  In battle:    Yes")
        gate = s['stage_gate']
        if gate == 0xFF:
            print(f"  Stage gate:   0xFF (always available)")
        else:
            stage_name = GAME_STAGES.get(gate, "")
            extra = f" = {stage_name}" if stage_name else ""
            print(f"  Stage gate:   0x{gate:02X}{extra}")
        print(f"  Appearance:   0x{s['appearance']:02X} ({s['appearance']})")
        print(f"  Troop ID:     {s['troop_id']}" + (" (none)" if s['troop_id'] == 0 else ""))
        print(f"  Coordinates:  ({s['coord1']}, {s['coord2']}) sign:{s['coord_sign']:02X} / pos:({s['pos_x']}, {s['pos_y']})")
        print(f"  Spice field:  {s['spice_field']}")
        print(f"  Spice amount: {s['spice_amount']}")
        print(f"  Spice dens:   {s['spice_density']}")
        print(f"  Equipment:    Harv={s['harvesters']} Orni={s['ornithopters']} "
              f"Knif={s['knives']} Gun={s['guns']} Weird={s['weirding']} "
              f"Atom={s['atomics']} Bulb={s['bulbs']}")
        print(f"  Byte0:        0x{s['byte0']:02X}")
        off = sav.sietch_offset(detail_idx)
        raw = ' '.join(f'{sav.data[off + i]:02X}' for i in range(SIETCH_SIZE))
        print(f"  Raw bytes:    {raw}")
        return

    print(f"\n=== Sietches ({SIETCH_COUNT} records) ===")
    hdr = "{:>3}  {:<22}  {:<14}  {:>3}  {:>5}  {:>5}  {:>5}  {}"
    print(hdr.format("#", "Name", "Status", "Trp", "SpcAm", "Dens", "SFld", "Equipment"))
    print("-" * 95)
    for i in range(SIETCH_COUNT):
        s = sav.sietch(i)
        # Build compact status flags
        flags = []
        if s['discovered']:  flags.append('D')
        if s['prospected']:  flags.append('P')
        if s['windtrap']:    flags.append('W')
        if s['inventory']:   flags.append('I')
        if s['vegetation']:  flags.append('V')
        if s['in_battle']:   flags.append('B')
        status = '|'.join(flags) or '-'
        equip = _equip_summary(s)
        print(hdr.format(
            i, s['name'], status, s['troop_id'],
            s['spice_amount'], s['spice_density'], s['spice_field'],
            equip,
        ))


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
