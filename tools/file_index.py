#!/usr/bin/env python3
"""
Dune 1992 Game File Index

Comprehensive catalog of all 186 HSQ game files with classification,
format details, and decoder tool references.

Usage:
  python3 file_index.py gamedata/            # Full index
  python3 file_index.py gamedata/ --category music     # Filter by category
  python3 file_index.py gamedata/ --summary            # Category summary
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress, hsq_get_sizes

# =============================================================================
# FILE CLASSIFICATION DATABASE
# =============================================================================

# Category → (description, decoder tool, file patterns/names)
CATEGORIES = {
    'music': {
        'desc': 'HERAD AdLib/OPL2 music',
        'tool': 'herad_decoder.py',
        'files': {'ARRAKIS', 'BAGDAD', 'CRYOMUS', 'MORNING', 'SEKENCE',
                  'SIETCHM', 'WARSONG', 'WATER', 'WORMINTR', 'WORMSUIT'},
    },
    'scene_bg': {
        'desc': 'Interior scene backgrounds (320×152 RLE)',
        'tool': 'sprite_decoder.py',
        'files': {'INT02', 'INT04', 'INT05', 'INT06', 'INT07', 'INT08',
                  'INT09', 'INT10', 'INT11', 'INT13', 'INT14', 'INT15'},
    },
    'character': {
        'desc': 'Character/NPC sprite sheets',
        'tool': 'sprite_decoder.py',
        'files': {'ATTACK', 'BACK', 'BALCON', 'BARO', 'BOOK', 'BOTA',
                  'BUNK', 'CHAN', 'CHANKISS', 'COMM', 'CORR', 'EMPR',
                  'EQUI', 'FEYD', 'FINAL', 'FRESK', 'FRM1', 'FRM2',
                  'FRM3', 'GENERIC', 'GURN', 'HARA', 'HARK', 'HAWA',
                  'IDAH', 'INTDS', 'JESS', 'KYNE', 'LETO', 'MIRROR',
                  'ONMAP', 'ORNYCAB', 'ORNYPAN', 'PAUL', 'PERS',
                  'PROUGE', 'SERRE', 'SIET1', 'SMUG', 'STIL', 'SUNRS',
                  'VER', 'VIS', 'XPLAIN9'},
    },
    'sprite': {
        'desc': 'UI/game sprite sheets',
        'tool': 'sprite_decoder.py',
        'files': {'ICONES', 'ORNY', 'ORNYTK', 'MIXR', 'MOIS', 'PALPLAN',
                  'POR', 'STARS', 'SKY', 'SKYDN'},
    },
    'landscape': {
        'desc': 'Landscape/scenery sprites',
        'tool': 'sprite_decoder.py',
        'prefixes': ['DF', 'DH', 'DP', 'DS', 'DV', 'DN2', 'DN3', 'VIL', 'SUN'],
    },
    'vga_sprite': {
        'desc': 'VGA overlay/effect sprites',
        'tool': 'sprite_decoder.py',
        'prefixes': ['VG'],
    },
    'animation': {
        'desc': 'LOP background animations (4-phase PackBits)',
        'tool': 'lop_decoder.py',
        'extensions': ['.LOP'],
    },
    'video': {
        'desc': 'HNM video sequences',
        'tool': 'hnm_decoder.py',
        'extensions': ['.HNM'],
    },
    'dialogue': {
        'desc': 'Dialogue/text system files',
        'tool': 'dialogue_browser.py',
        'files': {'DIALOGUE', 'CONDIT'},
    },
    'phrase': {
        'desc': 'Dialogue phrase text strings',
        'tool': 'phrase_dumper.py',
        'prefixes': ['PHRASE'],
    },
    'command': {
        'desc': 'Command/string tables',
        'tool': 'command_decoder.py',
        'prefixes': ['COMMAND'],
    },
    'map': {
        'desc': 'World map data',
        'tool': 'map_decoder.py',
        'files': {'MAP', 'MAP2'},
    },
    'sound': {
        'desc': 'Sound/audio data',
        'tool': None,
        'files': {'FREQ'},
        'prefixes': ['SN'],
    },
    'driver': {
        'desc': 'Hardware driver executables',
        'tool': None,
        'files': {'DN386', 'DNADG', 'DNADL', 'DNADP', 'DNMID',
                  'DNPCS', 'DNPCS2', 'DNSBP', 'DNSDB', 'DNVGA'},
    },
    'scene': {
        'desc': 'SAL scene layout definitions',
        'tool': 'sal_decoder.py',
        'files': {'PALAIS'},
    },
    'ruler': {
        'desc': 'Text ruler/banner graphics',
        'tool': 'sprite_decoder.py',
        'prefixes': ['IRUL'],
    },
    'data': {
        'desc': 'Game data/binary tables',
        'tool': 'bin_decoder.py',
        'files': {'GLOBDATA'},
    },
    'savegame': {
        'desc': 'Save game files (F7 RLE)',
        'tool': 'save_editor.py',
    },
    'other': {
        'desc': 'Non-game files',
        'tool': None,
    },
}


def classify_file(name_no_ext: str, ext: str) -> str:
    """Classify a game file into a category."""
    # Extension-based classification
    if ext == '.LOP':
        return 'animation'
    if ext == '.HNM':
        return 'video'
    if ext == '.AGD':
        return 'music'  # AdLib Gold variant
    if ext == '.M32':
        return 'music'  # MT-32/General MIDI variant
    if ext == '.SAL':
        return 'scene'
    if ext == '.SAV':
        return 'savegame'
    if ext == '.BIN':
        return 'data'

    # Skip non-game files
    if ext == '' or name_no_ext == '.gitkeep' or name_no_ext.startswith('.'):
        return 'other'

    # Name-based classification
    for cat_name, cat in CATEGORIES.items():
        if 'files' in cat and name_no_ext in cat['files']:
            return cat_name
        if 'prefixes' in cat:
            for prefix in cat['prefixes']:
                if name_no_ext.startswith(prefix):
                    return cat_name

    return 'unknown'


def scan_directory(dirpath: str) -> list:
    """Scan game data directory and classify all files."""
    results = []
    for fname in sorted(os.listdir(dirpath)):
        fpath = os.path.join(dirpath, fname)
        if not os.path.isfile(fpath):
            continue

        name_no_ext, ext = os.path.splitext(fname)
        ext = ext.upper()

        raw = open(fpath, 'rb').read()
        raw_size = len(raw)

        # Try HSQ decompression
        decomp_size = None
        if ext == '.HSQ':
            try:
                sizes = hsq_get_sizes(raw)
                decomp_size = sizes[0]
            except Exception:
                pass

        category = classify_file(name_no_ext, ext)
        cat_info = CATEGORIES.get(category, {'desc': 'Unclassified', 'tool': None})

        results.append({
            'filename': fname,
            'name': name_no_ext,
            'ext': ext,
            'raw_size': raw_size,
            'decomp_size': decomp_size,
            'category': category,
            'description': cat_info['desc'],
            'tool': cat_info.get('tool'),
        })

    return results


def show_index(results: list, category_filter: str = None):
    """Display full file index."""
    if category_filter:
        results = [r for r in results if r['category'] == category_filter]

    print(f"{'File':<16s} {'Raw':>7}  {'Decomp':>7}  {'Category':<12s}  {'Tool'}")
    print('-' * 72)

    for r in results:
        decomp = f"{r['decomp_size']:>7,}" if r['decomp_size'] else '     --'
        tool = r['tool'] or '--'
        print(f"{r['filename']:<16s} {r['raw_size']:>7,}  {decomp}  "
              f"{r['category']:<12s}  {tool}")

    print(f"\nTotal: {len(results)} files")


def show_summary(results: list):
    """Display category summary."""
    cats = {}
    for r in results:
        cat = r['category']
        if cat not in cats:
            cats[cat] = {'count': 0, 'total_raw': 0, 'desc': r['description'], 'tool': r['tool']}
        cats[cat]['count'] += 1
        cats[cat]['total_raw'] += r['raw_size']

    print(f"{'Category':<12s} {'Count':>5}  {'Size':>9}  {'Tool':<26s}  Description")
    print('-' * 90)

    for cat in sorted(cats.keys()):
        info = cats[cat]
        tool = info['tool'] or '--'
        print(f"{cat:<12s} {info['count']:>5}  {info['total_raw']:>9,}  "
              f"{tool:<26s}  {info['desc']}")

    total_files = sum(c['count'] for c in cats.values())
    total_size = sum(c['total_raw'] for c in cats.values())
    print(f"\n{'Total':<12s} {total_files:>5}  {total_size:>9,}")


def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 Game File Index',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('directory', help='Game data directory')
    p.add_argument('--category', '-c', help='Filter by category')
    p.add_argument('--summary', '-s', action='store_true',
                   help='Show category summary')
    args = p.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Not a directory: {args.directory}", file=sys.stderr)
        return 1

    results = scan_directory(args.directory)

    if args.summary:
        show_summary(results)
    else:
        show_index(results, args.category)

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
