#!/usr/bin/env python3
"""
Dune 1992 Dialogue Browser — CONDIT × DIALOGUE × PHRASE Integration Tool

Cross-references the three dialogue subsystems to show the complete
dialogue pipeline: who says what, under which conditions.

Pipeline:
  NPC.ForDialogue (byte 6 of NPC record) → DIALOGUE.HSQ entry index
  DIALOGUE entry: list of 4-byte records [cond_flags, condit_idx, phrase_info...]
  Each record gates a PHRASE text on a CONDIT condition:
    condit_idx → CONDIT.HSQ bytecode → evaluates to true/false
    phrase_idx → PHRASE*.HSQ text string to display

Usage:
  python3 dialogue_browser.py gamedata/         # Show all dialogue trees
  python3 dialogue_browser.py gamedata/ --npc 5 # Show dialogue for NPC #5
  python3 dialogue_browser.py gamedata/ --entry 9   # Show dialogue entry 9
  python3 dialogue_browser.py gamedata/ --search "spice"  # Search phrase text
  python3 dialogue_browser.py gamedata/ --stats     # Cross-reference statistics
  python3 dialogue_browser.py gamedata/ --lang 2    # French (default: 1=English)
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.compression import hsq_decompress
from lib.constants import (
    NPC_SPRITES, NPC_COUNT, NPC_STRIDE,
    GAME_STAGES, CONDIT_OPS, CONDIT_VARIABLES,
)


# =============================================================================
# RESOURCE LOADERS
# =============================================================================

def load_hsq(path: str) -> bytes:
    """Load and decompress an HSQ file."""
    with open(path, 'rb') as f:
        raw = f.read()
    return bytes(hsq_decompress(raw))


def load_offset_table(data: bytes) -> list:
    """Parse a standard offset table (first_offset/2 entries × uint16 LE)."""
    if len(data) < 2:
        return []
    first = struct.unpack_from('<H', data, 0)[0]
    count = first // 2
    offsets = []
    for i in range(count):
        if i * 2 + 1 >= len(data):
            break
        offsets.append(struct.unpack_from('<H', data, i * 2)[0])
    return offsets


# =============================================================================
# DIALOGUE PARSER
# =============================================================================

def parse_dialogue_entry(data: bytes, start: int) -> list:
    """Parse 4-byte dialogue records at offset `start` until 0xFFFF terminator.

    Record format (from DNCDPRG.EXE sub_19F9E):
      byte 0: flags (bit7=spoken, bit6=repeatable, bits3-0=action code)
      byte 1: NPC ID (low byte of CONDIT index)
      byte 2: bits7-6=cond_type, bits3-2=menu_flag, bits1-0=phrase_hi
      byte 3: phrase ID low byte
    """
    records = []
    pos = start
    while pos + 1 < len(data):
        word0 = struct.unpack_from('<H', data, pos)[0]
        if word0 == 0xFFFF:
            break
        if pos + 3 >= len(data):
            break
        b0, b1, b2, b3 = data[pos], data[pos + 1], data[pos + 2], data[pos + 3]
        cond_type = (b2 >> 6) & 0x03
        condit_idx = cond_type * 256 + b1  # full CONDIT index
        phrase_idx = ((b2 & 0x03) << 8) | b3
        records.append({
            'cond_flags': b0,
            'spoken': bool(b0 & 0x80),
            'repeatable': bool(b0 & 0x40),
            'action_code': b0 & 0x0F,
            'npc_id': b1,
            'cond_type': cond_type,
            'condit_idx': condit_idx,
            'menu_flag': (b2 >> 2) & 0x03,
            'phrase_idx': phrase_idx,
        })
        pos += 4
    return records


# =============================================================================
# CONDIT DECOMPILER (minimal inline version)
# =============================================================================

def decompile_condit(data: bytes, start: int) -> str:
    """Decompile a single CONDIT entry to expression string."""
    pos = start
    stack = []

    def read_operand(p):
        if p >= len(data):
            return "<EOF>", p
        tb = data[p]
        p += 1
        if tb < 0x80:
            if p >= len(data):
                return "<TRUNC>", p
            idx = data[p]
            p += 1
            byte_mode = (tb == 0x01)
            var_name = CONDIT_VARIABLES.get(idx, f"0x{idx:02X}")
            prefix = "byte" if byte_mode else "word"
            return f"{prefix}[{var_name}]", p
        elif tb == 0x80:
            if p >= len(data):
                return "<TRUNC>", p
            val = data[p]
            p += 1
            stage = GAME_STAGES.get(val)
            if stage:
                return f"0x{val:02X}/*{stage}*/", p
            return f"0x{val:02X}", p
        else:
            if p + 1 >= len(data):
                return "<TRUNC>", p
            val = struct.unpack_from('<H', data, p)[0]
            p += 2
            return f"0x{val:04X}", p

    acc, pos = read_operand(pos)

    while pos < len(data):
        b = data[pos]
        pos += 1
        if b == 0xFF:
            break
        elif b >= 0x80:
            op_idx = b & 0x1F
            op_info = CONDIT_OPS.get(op_idx)
            op_sym = op_info[1] if op_info else f"?{op_idx}"
            stack.append((acc, op_sym))
            acc, pos = read_operand(pos)
        else:
            op_idx = b & 0x1F
            op_info = CONDIT_OPS.get(op_idx)
            op_sym = op_info[1] if op_info else f"?{op_idx}"
            rhs, pos = read_operand(pos)
            acc = f"{acc} {op_sym} {rhs}"

    while stack:
        left, op_sym = stack.pop()
        acc = f"({left}) {op_sym} ({acc})"

    return acc


# =============================================================================
# PHRASE EXTRACTOR
# =============================================================================

def get_phrase(data: bytes, offsets: list, idx: int) -> str:
    """Extract phrase string by index."""
    if idx < 0 or idx >= len(offsets):
        return f"<IDX {idx} OUT OF RANGE>"
    start = offsets[idx]
    end = offsets[idx + 1] if idx + 1 < len(offsets) else len(data)
    if start >= len(data):
        return "<OUT OF RANGE>"
    raw = data[start:min(end, len(data))]
    # Strip trailing 0xFF
    while raw and raw[-1] == 0xFF:
        raw = raw[:-1]
    text = ''
    for b in raw:
        if b == 0xFF:
            text += ' | '
        elif b >= 0x20:
            text += chr(b)
        else:
            text += f'\\x{b:02X}'
    return text


# =============================================================================
# RESOURCE BUNDLE
# =============================================================================

class DialogueBundle:
    """Loads all dialogue resources from a game data directory."""

    def __init__(self, datadir: str, lang: int = 1):
        self.datadir = datadir
        self.lang = lang

        # Load DIALOGUE.HSQ
        dlg_path = os.path.join(datadir, 'DIALOGUE.HSQ')
        self.dlg_data = load_hsq(dlg_path)
        self.dlg_offsets = load_offset_table(self.dlg_data)

        # Load CONDIT.HSQ
        cnd_path = os.path.join(datadir, 'CONDIT.HSQ')
        self.cnd_data = load_hsq(cnd_path)
        self.cnd_offsets = load_offset_table(self.cnd_data)

        # Load PHRASE banks (bank 0 and bank 1 for selected language)
        self.phrase_data = {}
        self.phrase_offsets = {}
        for bank in [0, 1]:
            fname = f'PHRASE{lang}{bank + 1}.HSQ'
            phr_path = os.path.join(datadir, fname)
            if os.path.exists(phr_path):
                pdata = load_hsq(phr_path)
                poffsets = load_offset_table(pdata)
                self.phrase_data[bank] = pdata
                self.phrase_offsets[bank] = poffsets

    def get_dialogue_records(self, entry_idx: int) -> list:
        """Get parsed dialogue records for an entry."""
        if entry_idx < 0 or entry_idx >= len(self.dlg_offsets):
            return []
        return parse_dialogue_entry(self.dlg_data, self.dlg_offsets[entry_idx])

    def get_condition_expr(self, condit_idx: int) -> str:
        """Decompile a CONDIT condition to expression string."""
        if condit_idx >= len(self.cnd_offsets):
            return f"<CONDIT[0x{condit_idx:02X}] OUT OF RANGE>"
        off = self.cnd_offsets[condit_idx]
        # Check if empty
        end = self.cnd_offsets[condit_idx + 1] if condit_idx + 1 < len(self.cnd_offsets) else len(self.cnd_data)
        chunk = self.cnd_data[off:end]
        if all(b == 0 for b in chunk):
            return "(always true — empty condition)"
        return decompile_condit(self.cnd_data, off)

    def get_phrase_text(self, bank: int, phrase_idx: int) -> str:
        """Get phrase text from a bank."""
        if bank not in self.phrase_data:
            return f"<BANK {bank} NOT LOADED>"
        return get_phrase(self.phrase_data[bank], self.phrase_offsets[bank], phrase_idx)

    def record_flags_str(self, rec: dict) -> str:
        """Format record flags."""
        parts = []
        if rec.get('spoken'):
            parts.append("SPOKEN")
        if rec.get('repeatable'):
            parts.append("REPEAT")
        if rec.get('action_code'):
            parts.append(f"act={rec['action_code']}")
        if rec.get('menu_flag'):
            parts.append("MENU")
        return ' [' + '|'.join(parts) + ']' if parts else ''


# =============================================================================
# DISPLAY MODES
# =============================================================================

LANG_NAMES = {1: 'English', 2: 'French', 3: 'German', 4: 'Spanish',
              5: 'Italian', 6: 'Language6', 7: 'Language7'}


def show_entry(bundle: DialogueBundle, entry_idx: int):
    """Show detailed dialogue entry with conditions and phrases."""
    records = bundle.get_dialogue_records(entry_idx)
    if not records:
        print(f"Entry {entry_idx}: (empty)")
        return

    print(f"=== Dialogue Entry {entry_idx} ({len(records)} options) ===")
    for i, rec in enumerate(records):
        ci = rec['condit_idx']
        pi = rec['phrase_idx']
        ct = rec['cond_type']

        flags_str = bundle.record_flags_str(rec)
        cond_expr = bundle.get_condition_expr(ci)
        phrase_text = bundle.get_phrase_text(0, pi)

        ctype_label = "unconditional" if ct == 0 else f"type{ct}"
        print(f"\n  Option {i}:{flags_str}")
        print(f"    IF CONDIT[{ci}] ({ctype_label}): {cond_expr}")
        print(f"    THEN phrase[0x{pi:03X}]:")
        # Wrap long text
        if len(phrase_text) > 80:
            words = phrase_text.split()
            line = '      "'
            for w in words:
                if len(line) + len(w) + 1 > 90:
                    print(line)
                    line = '       ' + w
                else:
                    line += (' ' if len(line) > 7 else '') + w
            print(line + '"')
        else:
            print(f'      "{phrase_text}"')


def show_all(bundle: DialogueBundle):
    """Show all non-empty dialogue entries."""
    for idx in range(len(bundle.dlg_offsets)):
        records = bundle.get_dialogue_records(idx)
        if not records:
            continue
        show_entry(bundle, idx)
        print()


def show_npc(bundle: DialogueBundle, npc_idx: int, save_path: str = None):
    """Show dialogue for a specific NPC.

    If save_path is given, read the NPC's current ForDialogue from the save.
    Otherwise, show all possible dialogue entries for NPC sprite IDs.
    """
    if save_path:
        from lib.compression import f7_decompress
        with open(save_path, 'rb') as f:
            raw = f.read()
        save_data = f7_decompress(raw)
        npc_base = 0x53F4
        off = npc_base + npc_idx * NPC_STRIDE
        if off + 7 < len(save_data):
            sprite_id = save_data[off]
            for_dialogue = save_data[off + 6]
            name = NPC_SPRITES.get(sprite_id, f"Sprite 0x{sprite_id:02X}")
            print(f"NPC #{npc_idx}: {name}")
            print(f"  SpriteId=0x{sprite_id:02X}, ForDialogue={for_dialogue}")
            print()
            show_entry(bundle, for_dialogue)
        else:
            print(f"NPC #{npc_idx}: offset out of range in save")
        return

    # No save: show NPC info and note that ForDialogue is runtime
    name = NPC_SPRITES.get(npc_idx, f"NPC #{npc_idx}")
    print(f"NPC #{npc_idx}: {name}")
    print(f"  (ForDialogue index is stored in save file at 0x53F4 + {npc_idx}*16 + 6)")
    print(f"  Use --save <file> to read the actual dialogue entry from a save file.")
    print()

    # Show all dialogue entries that might be related
    # Scan for entries that reference conditions checking NPC-relevant stages
    print(f"  All dialogue entries (use --entry N for details):")
    for idx in range(len(bundle.dlg_offsets)):
        records = bundle.get_dialogue_records(idx)
        if records:
            condits = set(r['condit_idx'] for r in records)
            condits_str = ','.join(f'0x{c:02X}' for c in sorted(condits))
            print(f"    [{idx:3d}] {len(records):2d} options  condits={condits_str}")


def show_search(bundle: DialogueBundle, query: str):
    """Search all dialogue phrase text for a string."""
    query_lower = query.lower()
    matches = 0

    for entry_idx in range(len(bundle.dlg_offsets)):
        records = bundle.get_dialogue_records(entry_idx)
        if not records:
            continue

        for i, rec in enumerate(records):
            text = bundle.get_phrase_text(0, rec['phrase_idx'])
            if query_lower in text.lower():
                ci = rec['condit_idx']
                pi = rec['phrase_idx']
                ct = rec['cond_type']
                cond_expr = bundle.get_condition_expr(ci)
                ctype_label = "unconditional" if ct == 0 else f"type{ct}"
                print(f"Entry {entry_idx}, option {i}:")
                print(f"  IF CONDIT[{ci}] ({ctype_label}): {cond_expr}")
                print(f"  TEXT [0x{pi:03X}]: {text}")
                print()
                matches += 1

    print(f"Found {matches} matches for '{query}'")


def show_stats(bundle: DialogueBundle):
    """Show cross-reference statistics."""
    total_entries = len(bundle.dlg_offsets)
    non_empty = 0
    total_records = 0
    condit_usage = {}
    phrase_usage = {}
    cond_type_counts = {}
    repeatable_count = 0
    menu_count = 0

    for idx in range(total_entries):
        records = bundle.get_dialogue_records(idx)
        if not records:
            continue
        non_empty += 1
        total_records += len(records)

        for rec in records:
            ci = rec['condit_idx']
            condit_usage[ci] = condit_usage.get(ci, 0) + 1
            pi = rec['phrase_idx']
            phrase_usage[pi] = phrase_usage.get(pi, 0) + 1
            ct = rec['cond_type']
            cond_type_counts[ct] = cond_type_counts.get(ct, 0) + 1
            if rec.get('repeatable'):
                repeatable_count += 1
            if rec.get('menu_flag'):
                menu_count += 1

    # CONDIT coverage
    total_condit = len(bundle.cnd_offsets)
    used_condits = set(condit_usage.keys())

    # Phrase coverage
    phrase_counts = {}
    for bank in bundle.phrase_offsets:
        phrase_counts[bank] = len(bundle.phrase_offsets[bank])

    print(f"=== Dialogue System Cross-Reference Statistics ===")
    print(f"  Language: {LANG_NAMES.get(bundle.lang, 'Unknown')}")
    print()
    print(f"  DIALOGUE.HSQ:")
    print(f"    Total entries:     {total_entries}")
    print(f"    Non-empty entries: {non_empty}")
    print(f"    Total records:     {total_records}")
    print(f"    Avg records/entry: {total_records / non_empty:.1f}" if non_empty else "")
    print(f"    Repeatable:        {repeatable_count}")
    print(f"    One-shot:          {total_records - repeatable_count}")
    print(f"    Menu options:      {menu_count}")
    print()
    print(f"  Condition type distribution:")
    for ct in sorted(cond_type_counts):
        label = "unconditional" if ct == 0 else f"type {ct} (CONDIT[{ct*256}..{ct*256+255}])"
        print(f"    {label}: {cond_type_counts[ct]} records")
    print()
    print(f"  CONDIT.HSQ:")
    print(f"    Total conditions:  {total_condit}")
    print(f"    Used by dialogue:  {len(used_condits)}")
    print(f"    Unused:            {total_condit - len(used_condits)}")
    print()
    for bank in sorted(phrase_counts):
        print(f"  PHRASE (bank {bank}):")
        print(f"    Total strings:     {phrase_counts[bank]}")
    print(f"    Unique phrases used: {len(phrase_usage)}")
    print()
    print(f"  Top 15 most-used CONDIT conditions:")
    for ci, count in sorted(condit_usage.items(), key=lambda x: -x[1])[:15]:
        ct = ci // 256
        lo = ci % 256
        expr = bundle.get_condition_expr(ci)
        # Truncate long expressions
        if len(expr) > 55:
            expr = expr[:52] + "..."
        print(f"    [{ci:3d}] (type{ct}:0x{lo:02X}) {count:3d} refs: {expr}")

    print()
    print(f"  Game stage conditions breakdown:")
    stage_condits = {}
    for ci in used_condits:
        expr = bundle.get_condition_expr(ci)
        for stage_val, stage_name in GAME_STAGES.items():
            if f"0x{stage_val:02X}" in expr:
                stage_condits[stage_val] = stage_condits.get(stage_val, 0) + condit_usage[ci]
    for sv, count in sorted(stage_condits.items()):
        sname = GAME_STAGES.get(sv, "?")
        print(f"    Stage 0x{sv:02X} ({sname}): {count} dialogue records")


def show_stage_dialogue(bundle: DialogueBundle, stage_val: int):
    """Show all dialogue active at a specific game stage."""
    stage_name = GAME_STAGES.get(stage_val, f"0x{stage_val:02X}")
    print(f"=== Dialogue at Game Stage 0x{stage_val:02X} ({stage_name}) ===\n")

    # For each dialogue entry, check which options have conditions
    # that reference this stage value
    for entry_idx in range(len(bundle.dlg_offsets)):
        records = bundle.get_dialogue_records(entry_idx)
        if not records:
            continue

        relevant = []
        for i, rec in enumerate(records):
            expr = bundle.get_condition_expr(rec['condit_idx'])
            if f"0x{stage_val:02X}" in expr:
                relevant.append((i, rec, expr))

        if relevant:
            print(f"Entry {entry_idx}:")
            for i, rec, expr in relevant:
                text = bundle.get_phrase_text(0, rec['phrase_idx'])
                print(f"  [{i}] IF: {expr}")
                print(f"      TEXT: {text}")
            print()


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 Dialogue Browser — CONDIT × DIALOGUE × PHRASE',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('datadir', help='Game data directory containing HSQ files')
    p.add_argument('--lang', type=int, default=1, metavar='N',
                   help='Language (1=EN, 2=FR, 3=DE, 4=ES, 5=IT; default: 1)')
    p.add_argument('--entry', type=int, default=None, metavar='N',
                   help='Show specific dialogue entry')
    p.add_argument('--npc', type=int, default=None, metavar='N',
                   help='Show dialogue for NPC index (0-15)')
    p.add_argument('--save', type=str, default=None, metavar='FILE',
                   help='Save file to read NPC ForDialogue from (with --npc)')
    p.add_argument('--search', type=str, default=None, metavar='TEXT',
                   help='Search phrase text across all dialogue')
    p.add_argument('--stage', type=str, default=None, metavar='VAL',
                   help='Show dialogue active at game stage (decimal or 0x hex)')
    p.add_argument('--stats', action='store_true',
                   help='Show cross-reference statistics')
    args = p.parse_args()

    print(f"Loading dialogue resources (language={LANG_NAMES.get(args.lang, '?')})...")
    bundle = DialogueBundle(args.datadir, args.lang)
    print(f"  DIALOGUE: {len(bundle.dlg_offsets)} entries")
    print(f"  CONDIT:   {len(bundle.cnd_offsets)} conditions")
    for bank in sorted(bundle.phrase_offsets):
        print(f"  PHRASE bank {bank}: {len(bundle.phrase_offsets[bank])} strings")
    print()

    if args.entry is not None:
        show_entry(bundle, args.entry)
    elif args.npc is not None:
        show_npc(bundle, args.npc, args.save)
    elif args.search is not None:
        show_search(bundle, args.search)
    elif args.stage is not None:
        stage_val = int(args.stage, 0)
        show_stage_dialogue(bundle, stage_val)
    elif args.stats:
        show_stats(bundle)
    else:
        show_all(bundle)


if __name__ == '__main__':
    main()
