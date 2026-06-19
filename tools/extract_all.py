#!/usr/bin/env python
"""
Dune 1992 Batch Asset Extractor
=================================
Pipeline that extracts a whole gamedata directory into a flat, web-ready
output directory. Each asset is decoded with the appropriate existing tool and
written in an open format (PNG / WAV / JSON), plus a top-level manifest.json
cataloging everything produced.

Outputs (default ``extracted/``):
  - Sprite HSQ sheets        → <name>.png + <name>.json atlas (sprites/)
  - Sound effects (SN*)      → <name>.wav                     (audio/)
  - CONDIT.HSQ               → CONDIT.json                    (data/)
  - DIALOGUE.HSQ             → DIALOGUE.json                  (data/)
  - PHRASE*.HSQ              → <name>.json                    (text/)
  - COMMAND*.HSQ             → <name>.json                    (text/)
  - manifest.json            → catalog of all outputs (top level)

Robustness: every file is processed inside a try/except. Failures are logged
and skipped — one bad asset never aborts the whole run.

Usage:
  python extract_all.py                         # ./gamedata → ./extracted
  python extract_all.py --gamedata DIR --out DIR
  python extract_all.py --out /tmp/extracted    # custom output dir
"""

import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compression import hsq_decompress

import sprite_decoder
import sound_decoder
import condit_decompiler
import dialogue_decompiler
import phrase_dumper
import command_decoder


# =============================================================================
# CLASSIFICATION
# =============================================================================

def is_voc_payload(raw: bytes) -> bool:
    """True if raw bytes (or their HSQ-decompressed form) are a VOC file."""
    if raw[:20] == sound_decoder.VOC_MAGIC:
        return True
    try:
        dec = hsq_decompress(raw)
    except Exception:
        return False
    return dec[:20] == sound_decoder.VOC_MAGIC


# Safety bounds: bogus/non-sprite HSQ files can report enormous sprite counts
# and dimensions, which would OOM the decoder. Cap aggressively.
MAX_SPRITES = 2048
MAX_SPRITE_DIM = 1024            # any larger looks bogus for this game
MAX_TOTAL_SPRITE_AREA = 8_000_000  # ~8 MP across a whole sheet


def _sprite_header_dims(data: bytes, idx: int):
    """Read just a sprite's (width, height) from its header, no pixel decode.

    Returns (width, height) or None if the header can't be read. This lets us
    validate dimensions cheaply before the full (potentially huge) decode.
    """
    import struct
    pal_end = struct.unpack_from('<H', data, 0)[0]
    tbl = pal_end
    off_pos = tbl + idx * 2
    if off_pos + 1 >= len(data):
        return None
    sprite_off = struct.unpack_from('<H', data, off_pos)[0]
    base = tbl + sprite_off
    if base + 3 >= len(data):
        return None
    width = data[base] + ((data[base + 1] & 0x7F) << 8)
    height = data[base + 2]
    return width, height


def looks_like_sprite(data: bytes) -> bool:
    """Heuristic: does decompressed HSQ data parse as a real sprite sheet?

    A sprite file starts with a uint16 palette-end pointer; the offset table
    that follows yields a positive, bounded sprite count where the cheap header
    dimensions of EVERY sprite are sane and the cumulative area is bounded.
    Reads headers only (no pixel decode) so a bogus file can't OOM us here.
    """
    try:
        if len(data) < 8:
            return False
        n = sprite_decoder.count_sprites(data)
        if n <= 0 or n > MAX_SPRITES:
            return False
        good = 0
        total_area = 0
        for i in range(n):
            dims = _sprite_header_dims(data, i)
            if dims is None:
                return False  # truncated table → not a usable sprite sheet
            w, h = dims
            if w > MAX_SPRITE_DIM or h > MAX_SPRITE_DIM:
                return False
            total_area += w * h
            if total_area > MAX_TOTAL_SPRITE_AREA:
                return False
            if w > 0 and h > 0:
                good += 1
        return good > 0
    except Exception:
        return False


# =============================================================================
# PER-FILE EXTRACTORS (each returns a manifest entry dict or None)
# =============================================================================

def extract_sound(path: str, name: str, out_root: str) -> dict:
    """Decode a VOC/HSQ sound file and export a WAV."""
    raw = open(path, 'rb').read()
    if raw[:20] == sound_decoder.VOC_MAGIC:
        data = raw
    else:
        data = hsq_decompress(raw)
    if data[:20] != sound_decoder.VOC_MAGIC:
        raise ValueError("not a VOC payload")

    info = sound_decoder.parse_voc(bytes(data))
    audio_dir = os.path.join(out_root, 'audio')
    os.makedirs(audio_dir, exist_ok=True)
    sound_decoder.export_wav(path, bytes(data), audio_dir)

    base = os.path.splitext(name)[0]
    rel = os.path.join('audio', base + '.wav')
    return {
        'source': name, 'type': 'sound', 'output': rel,
        'sample_rate': info['sample_rate'],
        'duration': round(info['duration'], 3),
    }


def extract_sprites(path: str, name: str, out_root: str) -> dict:
    """Decode a sprite HSQ sheet → atlas PNG + JSON."""
    raw = open(path, 'rb').read()
    data = hsq_decompress(raw)
    n = sprite_decoder.count_sprites(data)
    import struct
    pal_end = struct.unpack_from('<H', data, 0)[0]
    palette = sprite_decoder.decode_palette(data, pal_end) if pal_end > 2 else {}

    base = os.path.splitext(name)[0]
    sprites_dir = os.path.join(out_root, 'sprites')
    atlas = sprite_decoder.export_atlas(data, n, palette, sprites_dir, base)

    return {
        'source': name, 'type': 'sprites',
        'output': os.path.join('sprites', base + '.png'),
        'atlas': os.path.join('sprites', base + '.json'),
        'sprite_count': len(atlas['sprites']),
        'palette_colors': atlas['palette_colors'],
    }


def _write_json(out_root: str, subdir: str, base: str, obj: dict) -> str:
    """Write obj as pretty JSON under out_root/subdir/base.json; return rel path."""
    d = os.path.join(out_root, subdir)
    os.makedirs(d, exist_ok=True)
    rel = os.path.join(subdir, base + '.json')
    with open(os.path.join(out_root, rel), 'w') as f:
        json.dump(obj, f, indent=2)
    return rel


def extract_condit(path: str, name: str, out_root: str) -> dict:
    """CONDIT.HSQ → JSON (reuses condit_decompiler.to_json_obj)."""
    data, count, offsets = condit_decompiler.load_condit(path, False)
    obj = condit_decompiler.to_json_obj(data, offsets, name, annotate=True)
    rel = _write_json(out_root, 'data', os.path.splitext(name)[0], obj)
    return {'source': name, 'type': 'condit', 'output': rel,
            'entry_count': count}


def extract_dialogue(path: str, name: str, out_root: str) -> dict:
    """DIALOGUE.HSQ → JSON (reuses dialogue_decompiler.to_json_obj)."""
    data, count, offsets = dialogue_decompiler.load_dialogue(path, False)
    obj = dialogue_decompiler.to_json_obj(data, offsets, name)
    rel = _write_json(out_root, 'data', os.path.splitext(name)[0], obj)
    return {'source': name, 'type': 'dialogue', 'output': rel,
            'entry_count': count}


def extract_phrase(path: str, name: str, out_root: str) -> dict:
    """PHRASE*.HSQ → JSON (reuses phrase_dumper.to_json_obj)."""
    data, count, offsets = phrase_dumper.load_phrase(path, False)
    obj = phrase_dumper.to_json_obj(data, offsets, name)
    rel = _write_json(out_root, 'text', os.path.splitext(name)[0], obj)
    return {'source': name, 'type': 'phrase', 'output': rel,
            'count': len(obj.get('phrases', []))}


def extract_command(path: str, name: str, out_root: str) -> dict:
    """COMMAND*.HSQ → JSON (string table)."""
    raw = open(path, 'rb').read()
    data = hsq_decompress(raw)
    strings = command_decoder.decode_strings(data)
    obj = {
        'file': name,
        'count': len(strings),
        'strings': [{'index': i, 'text': s} for i, s in enumerate(strings)],
    }
    rel = _write_json(out_root, 'text', os.path.splitext(name)[0], obj)
    return {'source': name, 'type': 'command', 'output': rel,
            'count': len(strings)}


# =============================================================================
# PIPELINE
# =============================================================================

def classify(name: str, path: str):
    """Pick an extractor for a file. Returns (kind_str, extractor_fn) or None."""
    upper = name.upper()
    base, ext = os.path.splitext(upper)
    raw = None  # lazy

    # Named special tables (content is HSQ).
    if upper == 'CONDIT.HSQ':
        return 'condit', extract_condit
    if upper == 'DIALOGUE.HSQ':
        return 'dialogue', extract_dialogue
    if base.startswith('PHRASE') and ext == '.HSQ':
        return 'phrase', extract_phrase
    if base.startswith('COMMAND') and ext == '.HSQ':
        return 'command', extract_command

    # Sound: SN*.HSQ / SN*.VOC, or any VOC payload.
    if ext == '.VOC':
        return 'sound', extract_sound
    if ext == '.HSQ' and base.startswith('SN'):
        return 'sound', extract_sound

    # Generic HSQ: probe for sprite content.
    if ext == '.HSQ':
        try:
            raw = open(path, 'rb').read()
            data = hsq_decompress(raw)
        except Exception:
            return None
        if looks_like_sprite(data):
            return 'sprites', extract_sprites
        # Could also be a VOC that wasn't named SN*.
        if data[:20] == sound_decoder.VOC_MAGIC:
            return 'sound', extract_sound
        return None

    return None


def run(gamedata: str, out_root: str) -> dict:
    """Extract everything under ``gamedata`` into ``out_root``.

    Returns the manifest dict (also written to out_root/manifest.json).
    """
    os.makedirs(out_root, exist_ok=True)

    files = sorted(
        f for f in os.listdir(gamedata)
        if not f.startswith('.') and os.path.isfile(os.path.join(gamedata, f))
    )

    entries = []
    skipped = []
    counts = {}

    for name in files:
        path = os.path.join(gamedata, name)
        decision = classify(name, path)
        if decision is None:
            skipped.append({'source': name, 'reason': 'no extractor / not decodable'})
            continue
        kind, fn = decision
        try:
            entry = fn(path, name, out_root)
            if entry:
                entries.append(entry)
                counts[kind] = counts.get(kind, 0) + 1
                print(f"  [{kind:8s}] {name} → {entry.get('output')}")
        except Exception as e:
            skipped.append({'source': name, 'reason': f'{type(e).__name__}: {e}'})
            print(f"  [SKIP    ] {name}: {type(e).__name__}: {e}", file=sys.stderr)

    manifest = {
        'gamedata': os.path.abspath(gamedata),
        'output': os.path.abspath(out_root),
        'total_inputs': len(files),
        'extracted': len(entries),
        'skipped': len(skipped),
        'counts_by_type': counts,
        'outputs': entries,
        'skipped_files': skipped,
    }

    with open(os.path.join(out_root, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=2)

    return manifest


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(
        description='Dune 1992 batch asset extractor (PNG/WAV/JSON + manifest)',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--gamedata', default='./gamedata', metavar='DIR',
                   help='Input game data directory (default: ./gamedata)')
    p.add_argument('--out', default='extracted', metavar='DIR',
                   help='Output directory (default: extracted)')
    args = p.parse_args()

    if not os.path.isdir(args.gamedata):
        print(f"Gamedata directory not found: {args.gamedata}", file=sys.stderr)
        return 1

    print(f"Extracting {args.gamedata} → {args.out}\n")
    try:
        manifest = run(args.gamedata, args.out)
    except Exception:
        # The run loop is internally guarded, but guard the framing too.
        traceback.print_exc()
        return 1

    print(f"\nDone: {manifest['extracted']} extracted, "
          f"{manifest['skipped']} skipped (of {manifest['total_inputs']} files)")
    print(f"By type: {manifest['counts_by_type']}")
    print(f"Manifest: {os.path.join(args.out, 'manifest.json')}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
