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
  - HNM videos               → <name>.png thumb + <name>.wav  (video/)
  - HERAD music (HSQ/AGD/M32)→ <name>_<ext>.mid               (music/)
  - LOP animations           → <name>/*.png                   (animations/)
  - SAL scenes               → <name>.json                    (scenes/)
  - MAP / MAP2               → <name>.png heatmap              (maps/)
  - DNCHAR fonts             → <name>.png glyph atlas          (fonts/)
  - TABLAT/VER/THE_END/GLOB  → <name>.json                    (data/)
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
from png import write_png

import sprite_decoder
import sound_decoder
import condit_decompiler
import dialogue_decompiler
import phrase_dumper
import command_decoder
import hnm_decoder
import herad_decoder
import lop_decoder
import sal_decoder
import map_decoder
import bin_decoder
import globdata_decoder

# HERAD music stems (each ships as .HSQ / .AGD / .M32).
HERAD_NAMES = {'ARRAKIS', 'BAGDAD', 'CRYOMUS', 'MORNING', 'SEKENCE',
               'SIETCHM', 'WARSONG', 'WATER', 'WORMINTR', 'WORMSUIT'}


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
        json.dump(obj, f, indent=2, default=str)
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


def extract_hnm(path: str, name: str, out_root: str) -> dict:
    """HNM video → first-frame PNG thumbnail + WAV soundtrack + metadata."""
    raw = open(path, 'rb').read()
    hnm = hnm_decoder.HnmFile(raw)
    base = os.path.splitext(name)[0]
    vdir = os.path.join(out_root, 'video')
    os.makedirs(vdir, exist_ok=True)
    entry = {'source': name, 'type': 'video', 'frames': hnm.frame_count}

    framebuf = bytearray(64000)  # 320×200
    palette = bytearray(hnm.palette)
    hnm.decode_frame(0, framebuf, palette)
    rgb = bytearray(64000 * 3)
    for i, p in enumerate(framebuf):
        o = i * 3
        b = p * 3
        rgb[o] = palette[b]
        rgb[o + 1] = palette[b + 1]
        rgb[o + 2] = palette[b + 2]
    png_rel = os.path.join('video', base + '.png')
    write_png(os.path.join(out_root, png_rel), 320, 200, bytes(rgb))
    entry['output'] = png_rel

    try:
        audio = hnm.extract_sound()
        if audio:
            wav_rel = os.path.join('video', base + '.wav')
            hnm_decoder.write_wav(os.path.join(out_root, wav_rel), bytes(audio))
            entry['audio'] = wav_rel
    except Exception:
        pass  # frame thumbnail still useful without audio
    return entry


def extract_herad(path: str, name: str, out_root: str) -> dict:
    """HERAD music (HSQ/AGD/M32) → Standard MIDI file."""
    raw = open(path, 'rb').read()
    data = hsq_decompress(raw) if (len(raw) >= 6 and (sum(raw[:6]) & 0xFF) == 0xAB) else raw
    mdir = os.path.join(out_root, 'music')
    os.makedirs(mdir, exist_ok=True)
    base, ext = os.path.splitext(name)
    # The three variants share a stem, so disambiguate by extension.
    rel = os.path.join('music', f"{base}_{ext.lstrip('.').lower()}.mid")
    herad_decoder.export_midi(name, bytes(data), os.path.join(out_root, rel))
    info = herad_decoder.parse_herad(bytes(data), name)
    return {'source': name, 'type': 'music', 'output': rel,
            'format': info['format'], 'tracks': info['n_tracks']}


def extract_lop(path: str, name: str, out_root: str) -> dict:
    """LOP background animation → per-section greyscale PNGs."""
    import glob as _glob
    data = open(path, 'rb').read()
    base = os.path.splitext(name)[0]
    rel_dir = os.path.join('animations', base)
    out_dir = os.path.join(out_root, rel_dir)
    lop_decoder.export_sections_png(name, data, out_dir)
    pngs = sorted(_glob.glob(os.path.join(out_dir, '*.png')))
    return {'source': name, 'type': 'animation', 'output': rel_dir,
            'sections': len(pngs)}


def extract_sal(path: str, name: str, out_root: str) -> dict:
    """SAL scene layout → structured JSON of every room section's commands."""
    data = open(path, 'rb').read()
    count, offsets, _ = sal_decoder.parse_sal(data)
    sections = []
    for i in range(count):
        off = offsets[i]
        end = offsets[i + 1] if i + 1 < count else len(data)
        try:
            sections.append(sal_decoder.decode_section(data, off, end))
        except Exception:
            sections.append(None)
    obj = {'file': name, 'section_count': count, 'sections': sections}
    rel = _write_json(out_root, 'scenes', os.path.splitext(name)[0], obj)
    return {'source': name, 'type': 'scene', 'output': rel, 'sections': count}


def extract_map(path: str, name: str, out_root: str) -> dict:
    """MAP/MAP2 HSQ → heatmap PNG."""
    raw = open(path, 'rb').read()
    data = hsq_decompress(raw)
    mdir = os.path.join(out_root, 'maps')
    os.makedirs(mdir, exist_ok=True)
    base = os.path.splitext(name)[0]
    rel = os.path.join('maps', base + '.png')
    res = map_decoder.render_map_png(bytes(data), os.path.join(out_root, rel))
    w = res[0] if isinstance(res, (tuple, list)) and res else None
    h = res[1] if isinstance(res, (tuple, list)) and len(res) > 1 else None
    return {'source': name, 'type': 'map', 'output': rel, 'width': w, 'height': h}


def extract_font(path: str, name: str, out_root: str) -> dict:
    """DNCHAR*.BIN bitmap font → glyph-atlas PNG."""
    data = open(path, 'rb').read()
    fdir = os.path.join(out_root, 'fonts')
    os.makedirs(fdir, exist_ok=True)
    base = os.path.splitext(name)[0]
    rel = os.path.join('fonts', base + '.png')
    bin_decoder.export_dnchar_png(data, os.path.join(out_root, rel))
    return {'source': name, 'type': 'font', 'output': rel}


def extract_bintable(path: str, name: str, out_root: str) -> dict:
    """TABLAT / VER / THE_END .BIN tables → JSON."""
    data = open(path, 'rb').read()
    up = name.upper()
    if up.startswith('TABLAT'):
        obj = {'file': name, 'table': bin_decoder.decode_tablat(data)}
    elif up.startswith('VER'):
        obj = {'file': name, 'info': bin_decoder.decode_ver(data)}
    elif up.startswith('THE_END'):
        obj = {'file': name, 'lines': bin_decoder.decode_the_end(data)}
    else:
        raise ValueError("unknown .BIN table")
    rel = _write_json(out_root, 'data', os.path.splitext(name)[0], obj)
    return {'source': name, 'type': 'data', 'output': rel}


def extract_globdata(path: str, name: str, out_root: str) -> dict:
    """GLOBDATA.HSQ → JSON of the gradient tables."""
    raw = open(path, 'rb').read()
    data = hsq_decompress(raw)
    tables = globdata_decoder.parse_gradient_tables(data)
    obj = {'file': name, 'gradient_table_count': len(tables), 'gradient_tables': tables}
    rel = _write_json(out_root, 'data', os.path.splitext(name)[0], obj)
    return {'source': name, 'type': 'data', 'output': rel,
            'gradient_tables': len(tables)}


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
    if upper in ('MAP.HSQ', 'MAP2.HSQ'):
        return 'map', extract_map
    if upper == 'GLOBDATA.HSQ':
        return 'globdata', extract_globdata

    # HERAD music: same stem ships as .HSQ / .AGD / .M32.
    if base in HERAD_NAMES and ext in ('.HSQ', '.AGD', '.M32'):
        return 'music', extract_herad

    # Container/media formats by extension.
    if ext == '.HNM':
        return 'video', extract_hnm
    if ext == '.LOP':
        return 'animation', extract_lop
    if ext == '.SAL':
        return 'scene', extract_sal
    if ext == '.BIN':
        if base.startswith('DNCHAR'):
            return 'font', extract_font
        if base.startswith('TABLAT') or base.startswith('VER') or base.startswith('THE_END'):
            return 'data', extract_bintable
        return None  # GLOBDATA.bin is a decompressed dup of the HSQ — skip

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
