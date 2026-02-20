#!/usr/bin/env python3
"""
Dune 1992 HERAD Music Format Decoder

Decodes HERAD (Hérault) AdLib/OPL2 music files used by Cryo Interactive.
HSQ-compressed; decompressed data uses a MIDI-like event stream format.

HERAD file structure (decompressed):
  Header:
    uint16 LE  instrument_block_offset (word 0)
    uint16 LE  track_offsets[N] (word 1..N, first is always 0x0032=50)
    uint16 LE  0x0000 (terminator)
    ...        zero padding to offset 0x2C
    Bytes 0x2C-0x2D: uint16 LE n_instruments
    Bytes 0x2E-0x2F: uint16 LE param2 (tempo/speed related?)
    Bytes 0x30-0x31: uint16 LE param3 (loop count?)

  Track data (offset 0x0032 to instrument_block_offset):
    Each track starts with a 2-byte header:
      byte 0: initial delay (single byte)
      byte 1: voice assignment (0x04 on track 0, 0xFF on tracks 1+)

    MIDI-like event stream per voice channel:
      90 NN VV = Note On (note number, velocity)
      80 NN VV = Note Off (note number, velocity)
      C0 II    = Program Change (instrument index)
      D0 PP VV = Control/Parameter change

    Delta time encoding:
      Status bytes (0x80, 0x90, 0xC0, 0xD0) can appear immediately
      after the previous event's data — implicit delta = 0.
      Otherwise, a VLQ-encoded delta time precedes the status byte.
      VLQ uses standard bit-7 continuation (0x82 0x0B = 267 ticks).
      Only bytes 0x81-0x8F appear as VLQ continuation in practice.

  Instrument definitions (at instrument_block_offset):
    OPL2 register data for AdLib FM synthesis
    11+ bytes per instrument (modulator + carrier registers + feedback)

Game music files (10 HERAD tracks):
  ARRAKIS.HSQ  - Main Arrakis theme
  BAGDAD.HSQ   - Smuggler/Baghdad theme
  CRYOMUS.HSQ  - Cryo logo jingle
  MORNING.HSQ  - Morning/dawn theme
  SEKENCE.HSQ  - Sequence/cutscene music
  SIETCHM.HSQ  - Sietch interior theme
  WARSONG.HSQ  - Battle/war music
  WATER.HSQ    - Water/ecology theme
  WORMINTR.HSQ - Worm encounter intro
  WORMSUIT.HSQ - Worm riding/stillsuit theme

Usage:
  python3 herad_decoder.py gamedata/ARRAKIS.HSQ           # Analyze single file
  python3 herad_decoder.py gamedata/*.HSQ --stats          # Summary of all HERAD files
  python3 herad_decoder.py gamedata/ARRAKIS.HSQ --tracks   # Show track details
  python3 herad_decoder.py gamedata/ARRAKIS.HSQ --events 0 # Dump events for track 0
  python3 herad_decoder.py gamedata/ARRAKIS.HSQ --raw      # Already decompressed
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress


# =============================================================================
# HERAD CONSTANTS
# =============================================================================

HERAD_SIGNATURE = 0x0032  # Always at word 1 (bytes 2-3)
HEADER_DATA_START = 0x0032  # Track data always starts at byte 50
HEADER_META_OFFSET = 0x2C  # Metadata at bytes 44-49

# MIDI-like event types
EVT_NOTE_OFF = 0x80
EVT_NOTE_ON = 0x90
EVT_PROG_CHANGE = 0xC0
EVT_CONTROL = 0xD0

# Note names for display
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def note_name(note_num: int) -> str:
    """Convert MIDI note number to name (e.g. 0x37=55 → G3)."""
    octave = (note_num // 12) - 1
    name = NOTE_NAMES[note_num % 12]
    return f"{name}{octave}"


# =============================================================================
# HERAD PARSER
# =============================================================================

def parse_herad(data: bytes) -> dict:
    """Parse HERAD file structure from decompressed data."""
    if len(data) < HEADER_DATA_START:
        raise ValueError(f"File too small ({len(data)} bytes, need {HEADER_DATA_START})")

    # Word 0: instrument block offset
    inst_offset = struct.unpack_from('<H', data, 0)[0]

    # Words 1+: track offsets (starting with 0x0032)
    track_offsets = []
    for i in range(1, 11):  # max 10 entries (9 OPL voices + 1 base)
        if i * 2 + 1 >= len(data):
            break
        off = struct.unpack_from('<H', data, i * 2)[0]
        if off == 0:
            break
        track_offsets.append(off)

    # Metadata at 0x2C
    n_instruments = struct.unpack_from('<H', data, HEADER_META_OFFSET)[0]
    meta_param2 = struct.unpack_from('<H', data, HEADER_META_OFFSET + 2)[0]
    meta_param3 = struct.unpack_from('<H', data, HEADER_META_OFFSET + 4)[0]

    # Compute track sizes
    tracks = []
    for ti in range(len(track_offsets)):
        start = track_offsets[ti]
        if ti + 1 < len(track_offsets):
            end = track_offsets[ti + 1]
        else:
            end = inst_offset
        if start < len(data) and end <= len(data):
            tracks.append({
                'index': ti,
                'offset': start,
                'size': end - start,
                'data': data[start:end],
            })

    # Instrument data
    inst_size = len(data) - inst_offset if inst_offset < len(data) else 0
    inst_data = data[inst_offset:] if inst_offset < len(data) else b''

    return {
        'file_size': len(data),
        'inst_offset': inst_offset,
        'track_offsets': track_offsets,
        'n_tracks': len(tracks),
        'tracks': tracks,
        'n_instruments': n_instruments,
        'meta_param2': meta_param2,
        'meta_param3': meta_param3,
        'inst_size': inst_size,
        'inst_data': inst_data,
    }


def read_vlq(data: bytes, pos: int) -> tuple:
    """Read a MIDI variable-length quantity. Returns (value, new_pos)."""
    value = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        value = (value << 7) | (b & 0x7F)
        if not (b & 0x80):
            break
    return value, pos


def is_status_byte(b: int) -> bool:
    """Check if a byte is a HERAD status byte (not a delta/data byte).

    HERAD uses exactly four MIDI-like status bytes:
      0x80 = Note Off, 0x90 = Note On, 0xC0 = Program Change, 0xD0 = Control
    Plus 0xFF for voice/sync markers.
    Unlike standard MIDI which uses channels (0x80-0x8F, etc.), HERAD uses
    only the base values — the OPL2 voice is determined by the track index.
    """
    return b in (0x80, 0x90, 0xC0, 0xD0, 0xFF)


def parse_track_events(track_data: bytes) -> list:
    """Parse MIDI-like events from track data.

    Track structure: [initial_delta] [voice_byte] [events...]

    The first two bytes are a track header:
      byte 0: initial delay (single byte, 0x00-0x7F)
      byte 1: voice/channel assignment (0x04 on track 0, 0xFF on others)

    Subsequent events follow these parsing rules:
      - If next byte is a status byte (0x80/0x90/0xC0/0xD0/0xFF), the event
        has implicit delta=0 (no delay before it)
      - Otherwise, read a VLQ-encoded delta time, then read the status byte
      - Event data bytes follow the status byte (1-2 bytes depending on type)
      - Track boundary is determined by the offset table, not by in-stream markers

    Returns list of (delta_time, event_type, event_data) tuples.
    """
    events = []
    pos = 0

    while pos < len(track_data):
        b = track_data[pos]

        if is_status_byte(b):
            # Status byte directly → implicit delta = 0
            delta = 0
            status = b
        else:
            # Read delta time (VLQ for multi-byte, or single byte if < 0x80)
            delta, pos = read_vlq(track_data, pos)
            if pos >= len(track_data):
                break
            status = track_data[pos]

        # Process event based on status byte
        if status == 0x90:
            # Note On: status + note + velocity
            if pos + 2 >= len(track_data):
                break
            note = track_data[pos + 1]
            vel = track_data[pos + 2]
            events.append((delta, 'NOTE_ON', [note, vel]))
            pos += 3
        elif status == 0x80:
            # Note Off: status + note + velocity
            if pos + 2 >= len(track_data):
                break
            note = track_data[pos + 1]
            vel = track_data[pos + 2]
            events.append((delta, 'NOTE_OFF', [note, vel]))
            pos += 3
        elif status == 0xC0:
            # Program Change: status + instrument
            if pos + 1 >= len(track_data):
                break
            prog = track_data[pos + 1]
            events.append((delta, 'PROG_CHG', [prog]))
            pos += 2
        elif status == 0xD0:
            # Control/parameter: status + param + value
            if pos + 2 >= len(track_data):
                break
            param = track_data[pos + 1]
            value = track_data[pos + 2]
            events.append((delta, 'CONTROL', [param, value]))
            pos += 3
        elif status == 0xFF:
            # Voice/sync marker (single byte)
            events.append((delta, 'VOICE', [status]))
            pos += 1
        else:
            # Unknown single-byte command (0x04 = voice assignment on track 0)
            events.append((delta, 'VOICE', [status]))
            pos += 1

    return events


# =============================================================================
# DISPLAY MODES
# =============================================================================

def show_file(filepath: str, data: bytes):
    """Analyze a HERAD music file."""
    fname = os.path.basename(filepath)
    info = parse_herad(data)

    track_data_size = info['inst_offset'] - HEADER_DATA_START
    print(f"=== {fname} ({info['file_size']:,} bytes decompressed) ===")
    print(f"  Tracks:           {info['n_tracks']}")
    print(f"  Instruments:      {info['n_instruments']}")
    print(f"  Param2 (tempo?):  {info['meta_param2']}")
    print(f"  Param3 (loops?):  {info['meta_param3']}")
    print(f"  Track data:       0x{HEADER_DATA_START:04X}-0x{info['inst_offset']:04X} "
          f"({track_data_size:,} bytes)")
    print(f"  Instrument data:  0x{info['inst_offset']:04X}-0x{info['file_size']:04X} "
          f"({info['inst_size']:,} bytes)")

    # Per-track summary
    total_notes = 0
    print(f"\n  {'Track':>5}  {'Offset':>8}  {'Size':>6}  {'Notes':>5}  {'Events':>6}  {'Duration':>8}")
    print(f"  {'-----':>5}  {'--------':>8}  {'------':>6}  {'-----':>5}  {'------':>6}  {'--------':>8}")

    for track in info['tracks']:
        events = parse_track_events(track['data'])
        note_ons = sum(1 for _, etype, _ in events if etype == 'NOTE_ON')
        total_ticks = sum(delta for delta, _, _ in events)
        total_notes += note_ons

        print(f"  {track['index']:5d}  0x{track['offset']:04X}  {track['size']:6,}  "
              f"{note_ons:5d}  {len(events):6d}  {total_ticks:8,} ticks")

    print(f"\n  Total notes: {total_notes}")


def show_tracks(filepath: str, data: bytes):
    """Show detailed track information."""
    fname = os.path.basename(filepath)
    info = parse_herad(data)

    print(f"=== {fname} Track Details ===\n")

    for track in info['tracks']:
        events = parse_track_events(track['data'])

        note_ons = [e for _, etype, e in events if etype == 'NOTE_ON']
        note_offs = [e for _, etype, e in events if etype == 'NOTE_OFF']
        prog_chgs = [e for _, etype, e in events if etype == 'PROG_CHG']
        controls = [e for _, etype, e in events if etype == 'CONTROL']

        # Note range
        all_notes = [n[0] for n in note_ons] + [n[0] for n in note_offs]
        note_range = ""
        if all_notes:
            lo, hi = min(all_notes), max(all_notes)
            note_range = f"{note_name(lo)}-{note_name(hi)} ({lo}-{hi})"

        # Velocity stats
        velocities = [n[1] for n in note_ons if n[1] > 0]
        vel_str = ""
        if velocities:
            vel_str = f"vel {min(velocities)}-{max(velocities)}"

        print(f"Track {track['index']}:")
        print(f"  Offset: 0x{track['offset']:04X}, Size: {track['size']:,} bytes")
        print(f"  Events: {len(events)} ({len(note_ons)} notes, {len(controls)} controls)")
        if note_range:
            print(f"  Notes:  {note_range} {vel_str}")
        if prog_chgs:
            instruments = [p[0] for p in prog_chgs]
            print(f"  Instruments: {', '.join(str(i) for i in instruments)}")
        print()


def show_events(filepath: str, data: bytes, track_idx: int):
    """Dump all events for a specific track."""
    fname = os.path.basename(filepath)
    info = parse_herad(data)

    if track_idx >= len(info['tracks']):
        print(f"Track {track_idx} out of range (0-{len(info['tracks'])-1})",
              file=sys.stderr)
        return

    track = info['tracks'][track_idx]
    events = parse_track_events(track['data'])

    print(f"=== {fname} Track {track_idx} Events ===")
    print(f"  Offset: 0x{track['offset']:04X}, Size: {track['size']:,} bytes")
    print(f"  Events: {len(events)}\n")

    print(f"  {'#':>4}  {'Delta':>7}  {'Abs':>9}  {'Type':>10}  Details")
    print(f"  {'----':>4}  {'-------':>7}  {'---------':>9}  {'----------':>10}  -------")

    abs_time = 0
    for i, (delta, etype, edata) in enumerate(events):
        abs_time += delta
        detail = ""

        if etype == 'NOTE_ON':
            nn = note_name(edata[0])
            detail = f"note={nn} ({edata[0]})  vel={edata[1]}"
        elif etype == 'NOTE_OFF':
            nn = note_name(edata[0])
            detail = f"note={nn} ({edata[0]})  vel={edata[1]}"
        elif etype == 'PROG_CHG':
            detail = f"instrument={edata[0]}"
        elif etype == 'CONTROL':
            detail = f"param=0x{edata[0]:02X}  value={edata[1]}"
        elif etype == 'VOICE':
            if edata[0] == 0xFF:
                detail = "voice=0xFF (sync/default)"
            else:
                detail = f"voice=0x{edata[0]:02X}"

        print(f"  {i:4d}  {delta:7d}  {abs_time:9d}  {etype:>10}  {detail}")


def show_stats(filepaths: list):
    """Show summary statistics for multiple HERAD files."""
    print(f"{'File':<14} {'Size':>7}  {'Tracks':>6}  {'Instr':>5}  "
          f"{'Notes':>6}  {'P2':>4}  {'P3':>3}")
    print('-' * 56)

    for filepath in filepaths:
        raw = open(filepath, 'rb').read()
        try:
            data = hsq_decompress(raw)
        except Exception:
            continue

        # Verify HERAD signature
        if len(data) < HEADER_DATA_START:
            continue
        sig = struct.unpack_from('<H', data, 2)[0]
        if sig != HERAD_SIGNATURE:
            continue

        fname = os.path.basename(filepath)
        info = parse_herad(data)

        total_notes = 0
        for track in info['tracks']:
            events = parse_track_events(track['data'])
            total_notes += sum(1 for _, etype, _ in events if etype == 'NOTE_ON')

        print(f"{fname:<14} {info['file_size']:>7,}  {info['n_tracks']:>6}  "
              f"{info['n_instruments']:>5}  {total_notes:>6}  "
              f"{info['meta_param2']:>4}  {info['meta_param3']:>3}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 HERAD Music Format Decoder',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('files', nargs='+', help='HERAD HSQ music file(s)')
    p.add_argument('--raw', action='store_true',
                   help='Input is already decompressed')
    p.add_argument('--tracks', action='store_true',
                   help='Show detailed track information')
    p.add_argument('--events', type=int, default=None, metavar='N',
                   help='Dump events for track N')
    p.add_argument('--stats', action='store_true',
                   help='Show summary statistics for all files')
    args = p.parse_args()

    if args.stats:
        show_stats(args.files)
        return 0

    for filepath in args.files:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}", file=sys.stderr)
            continue

        raw = open(filepath, 'rb').read()
        if args.raw:
            data = raw
        else:
            try:
                data = hsq_decompress(raw)
            except Exception:
                print(f"HSQ decompression failed for {filepath}", file=sys.stderr)
                continue

        # Verify HERAD signature
        if len(data) >= 4:
            sig = struct.unpack_from('<H', data, 2)[0]
            if sig != HERAD_SIGNATURE:
                print(f"Not a HERAD file: {filepath} (signature=0x{sig:04X}, "
                      f"expected 0x{HERAD_SIGNATURE:04X})", file=sys.stderr)
                continue

        data = bytes(data)

        if args.events is not None:
            show_events(filepath, data, args.events)
        elif args.tracks:
            show_tracks(filepath, data)
        else:
            show_file(filepath, data)

        print()

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
