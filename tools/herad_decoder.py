#!/usr/bin/env python
"""
Dune 1992 HERAD Music Format Decoder

Decodes HERAD (Hérault) music files used by Cryo Interactive in three variants:
  - HSQ (OPL2/AdLib): 9 tracks, status bytes 0x80/0x90/0xC0/0xD0
  - AGD (Tandy/PCjr): same as HSQ with 32-byte extra header at 0x32-0x51
  - M32 (Roland MT-32): 1 track, standard MIDI channelized status bytes

HERAD file structure (decompressed):
  Header:
    uint16 LE  instrument_block_offset (word 0)
    uint16 LE  track_offsets[N] (word 1..N, first is 0x0032 or 0x0052)
    uint16 LE  0x0000 (terminator)
    ...        zero padding to offset 0x2C
    Bytes 0x2C-0x2D: uint16 LE n_instruments
    Bytes 0x2E-0x2F: uint16 LE param2 (tempo/speed related?)
    Bytes 0x30-0x31: uint16 LE param3 (loop count?)

  AGD extra params (0x32-0x51, only in AGD files with data_start=0x52):
    32 bytes of Tandy/PCjr-specific channel configuration

  Track data (offset data_start to instrument_block_offset):
    Each track starts with a 2-byte header:
      byte 0: initial delay (single byte)
      byte 1: voice assignment (0x04 on track 0, 0xFF on tracks 1+)

    HSQ/AGD event stream (OPL2, no channel in status byte):
      90 NN VV = Note On (note number, velocity)
      80 NN VV = Note Off (note number, velocity)
      C0 II    = Program Change (instrument index)
      D0 PP VV = Control/Parameter change

    M32 event stream (MIDI channelized status bytes):
      9N NN VV = Note On (channel N)
      8N NN VV = Note Off (channel N)
      BN CC VV = Control Change (channel N)
      CN PP    = Program Change (channel N)
      EN LL MM = Pitch Bend (channel N)

    Delta time encoding:
      Status bytes (>= 0x80) can appear immediately with implicit delta = 0.
      Otherwise, a VLQ-encoded delta time precedes the status byte.

  Instrument definitions (at instrument_block_offset):
    OPL2 register data for AdLib FM synthesis (HSQ/AGD)
    MT-32 patch data (M32)

Game music files (10 tracks x 3 variants = 30 files):
  ARRAKIS   - Main Arrakis theme       MORNING  - Morning/dawn theme
  BAGDAD    - Smuggler theme            SEKENCE  - Cutscene music
  CRYOMUS   - Cryo logo jingle          SIETCHM  - Sietch interior
  WARSONG   - Battle music              WATER    - Ecology theme
  WORMINTR  - Worm encounter            WORMSUIT - Worm riding

Usage:
  python herad_decoder.py gamedata/ARRAKIS.HSQ           # Analyze single file
  python herad_decoder.py gamedata/ARRAKIS.AGD           # Analyze AGD variant
  python herad_decoder.py gamedata/ARRAKIS.M32           # Analyze M32 variant
  python herad_decoder.py gamedata/*.HSQ --stats          # Summary of all files
  python herad_decoder.py gamedata/ARRAKIS.HSQ --tracks   # Show track details
  python herad_decoder.py gamedata/ARRAKIS.HSQ --events 0 # Dump events for track 0
  python herad_decoder.py gamedata/ARRAKIS.HSQ --midi DIR # Export to MIDI
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

HERAD_DATA_START_OPL2 = 0x0032  # HSQ/M32: track data starts at byte 50
HERAD_DATA_START_AGD = 0x0052   # AGD: track data starts at byte 82
HEADER_META_OFFSET = 0x2C       # Metadata at bytes 44-49 (same for all variants)

# Format types
FMT_OPL2 = 'OPL2'    # HSQ files (AdLib/Sound Blaster)
FMT_AGD = 'AGD'       # Tandy/PCjr
FMT_M32 = 'M32'       # Roland MT-32/LAPC-I

# Note names for display
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def note_name(note_num: int) -> str:
    """Convert MIDI note number to name (e.g. 0x37=55 -> G3)."""
    octave = (note_num // 12) - 1
    name = NOTE_NAMES[note_num % 12]
    return f"{name}{octave}"


# =============================================================================
# HERAD PARSER
# =============================================================================

def detect_format(data: bytes, filepath: str = '') -> str:
    """Detect HERAD variant from file extension and header signature.

    Returns format type string: FMT_OPL2, FMT_AGD, or FMT_M32.
    """
    ext = os.path.splitext(filepath)[1].upper() if filepath else ''

    if ext == '.M32':
        return FMT_M32
    if ext == '.AGD':
        return FMT_AGD

    # Check header signature for non-extension detection
    if len(data) >= 4:
        sig = struct.unpack_from('<H', data, 2)[0]
        if sig == HERAD_DATA_START_AGD:
            return FMT_AGD

    return FMT_OPL2


def get_data_start(fmt: str, data: bytes) -> int:
    """Get track data start offset for the given format.

    HSQ/M32 always use 0x0032. AGD uses the signature word at offset 2,
    which is 0x0052 for most files but 0x0032 for CRYOMUS.AGD.
    """
    if fmt == FMT_AGD:
        sig = struct.unpack_from('<H', data, 2)[0]
        return sig  # 0x0052 or 0x0032
    return HERAD_DATA_START_OPL2


def is_herad_file(data: bytes, filepath: str = '') -> bool:
    """Check if data is a valid HERAD file."""
    if len(data) < HERAD_DATA_START_OPL2:
        return False
    sig = struct.unpack_from('<H', data, 2)[0]
    ext = os.path.splitext(filepath)[1].upper() if filepath else ''
    # Accept both 0x0032 and 0x0052 as valid signatures
    if sig == HERAD_DATA_START_OPL2 or sig == HERAD_DATA_START_AGD:
        return True
    # Also accept AGD/M32 by extension
    if ext in ('.AGD', '.M32'):
        return True
    return False


def parse_herad(data: bytes, filepath: str = '') -> dict:
    """Parse HERAD file structure from decompressed data."""
    fmt = detect_format(data, filepath)
    data_start = get_data_start(fmt, data)

    if len(data) < data_start:
        raise ValueError(f"File too small ({len(data)} bytes, need {data_start})")

    # Word 0: instrument block offset
    inst_offset = struct.unpack_from('<H', data, 0)[0]

    # Words 1+: track offsets
    track_offsets = []
    max_tracks = 20 if fmt == FMT_AGD else 11
    for i in range(1, max_tracks):
        if i * 2 + 1 >= min(len(data), HEADER_META_OFFSET):
            break
        off = struct.unpack_from('<H', data, i * 2)[0]
        if off == 0:
            break
        track_offsets.append(off)

    # Metadata at 0x2C (same position for all variants)
    n_instruments = struct.unpack_from('<H', data, HEADER_META_OFFSET)[0]
    meta_param2 = struct.unpack_from('<H', data, HEADER_META_OFFSET + 2)[0]
    meta_param3 = struct.unpack_from('<H', data, HEADER_META_OFFSET + 4)[0]

    # AGD extra params
    agd_params = None
    if fmt == FMT_AGD and data_start == HERAD_DATA_START_AGD:
        agd_params = data[HERAD_DATA_START_OPL2:HERAD_DATA_START_AGD]

    # Compute track sizes
    tracks = []
    for ti in range(len(track_offsets)):
        start = track_offsets[ti]
        if ti + 1 < len(track_offsets):
            end = track_offsets[ti + 1]
        else:
            end = inst_offset
        if start < len(data) and end <= len(data) and end > start:
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
        'format': fmt,
        'data_start': data_start,
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
        'agd_params': agd_params,
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


def is_status_byte_opl2(b: int) -> bool:
    """Check if byte is an OPL2 HERAD status byte (HSQ/AGD format)."""
    return b in (0x80, 0x90, 0xC0, 0xD0, 0xFF)


def is_status_byte_m32(b: int) -> bool:
    """Check if byte is an M32/MIDI status byte (>= 0x80)."""
    return b >= 0x80


def parse_track_events(track_data: bytes, fmt: str = FMT_OPL2) -> list:
    """Parse MIDI-like events from track data.

    For OPL2/AGD: uses fixed status bytes (0x80, 0x90, 0xC0, 0xD0).
    For M32: uses standard MIDI channelized status bytes (0x8N-0xFN).

    Returns list of (delta_time, event_type, event_data) tuples.
    event_data includes channel for M32 format.
    """
    events = []
    pos = 0
    is_status = is_status_byte_m32 if fmt == FMT_M32 else is_status_byte_opl2

    while pos < len(track_data):
        b = track_data[pos]

        if is_status(b):
            delta = 0
            status = b
        else:
            delta, pos = read_vlq(track_data, pos)
            if pos >= len(track_data):
                break
            status = track_data[pos]

        if fmt == FMT_M32:
            # Standard MIDI: channel embedded in status byte
            msg_type = status & 0xF0
            channel = status & 0x0F

            if msg_type == 0x90:
                if pos + 2 >= len(track_data):
                    break
                note = track_data[pos + 1]
                vel = track_data[pos + 2]
                events.append((delta, 'NOTE_ON', [note, vel, channel]))
                pos += 3
            elif msg_type == 0x80:
                if pos + 2 >= len(track_data):
                    break
                note = track_data[pos + 1]
                vel = track_data[pos + 2]
                events.append((delta, 'NOTE_OFF', [note, vel, channel]))
                pos += 3
            elif msg_type == 0xC0:
                if pos + 1 >= len(track_data):
                    break
                prog = track_data[pos + 1]
                events.append((delta, 'PROG_CHG', [prog, channel]))
                pos += 2
            elif msg_type == 0xB0:
                if pos + 2 >= len(track_data):
                    break
                cc = track_data[pos + 1]
                val = track_data[pos + 2]
                events.append((delta, 'CONTROL', [cc, val, channel]))
                pos += 3
            elif msg_type == 0xE0:
                if pos + 2 >= len(track_data):
                    break
                lsb = track_data[pos + 1]
                msb = track_data[pos + 2]
                events.append((delta, 'PITCH_BEND', [lsb, msb, channel]))
                pos += 3
            elif msg_type == 0xD0:
                if pos + 1 >= len(track_data):
                    break
                pressure = track_data[pos + 1]
                events.append((delta, 'AFTERTOUCH', [pressure, channel]))
                pos += 2
            elif status == 0xFF:
                events.append((delta, 'VOICE', [status]))
                pos += 1
            elif msg_type == 0xF0:
                # SysEx or system message — skip to end marker 0xF7
                pos += 1
                while pos < len(track_data) and track_data[pos] != 0xF7:
                    pos += 1
                if pos < len(track_data):
                    pos += 1  # skip 0xF7
            else:
                events.append((delta, 'UNKNOWN', [status]))
                pos += 1
        else:
            # OPL2/AGD: fixed status bytes
            if status == 0x90:
                if pos + 2 >= len(track_data):
                    break
                note = track_data[pos + 1]
                vel = track_data[pos + 2]
                events.append((delta, 'NOTE_ON', [note, vel]))
                pos += 3
            elif status == 0x80:
                if pos + 2 >= len(track_data):
                    break
                note = track_data[pos + 1]
                vel = track_data[pos + 2]
                events.append((delta, 'NOTE_OFF', [note, vel]))
                pos += 3
            elif status == 0xC0:
                if pos + 1 >= len(track_data):
                    break
                prog = track_data[pos + 1]
                events.append((delta, 'PROG_CHG', [prog]))
                pos += 2
            elif status == 0xD0:
                if pos + 2 >= len(track_data):
                    break
                param = track_data[pos + 1]
                value = track_data[pos + 2]
                events.append((delta, 'CONTROL', [param, value]))
                pos += 3
            elif status == 0xFF:
                events.append((delta, 'VOICE', [status]))
                pos += 1
            else:
                events.append((delta, 'VOICE', [status]))
                pos += 1

    return events


# =============================================================================
# DISPLAY MODES
# =============================================================================

FORMAT_LABELS = {
    FMT_OPL2: 'OPL2/AdLib',
    FMT_AGD: 'Tandy/PCjr',
    FMT_M32: 'Roland MT-32',
}


def show_file(filepath: str, data: bytes):
    """Analyze a HERAD music file."""
    fname = os.path.basename(filepath)
    info = parse_herad(data, filepath)
    fmt = info['format']

    track_data_size = info['inst_offset'] - info['data_start']
    print(f"=== {fname} ({info['file_size']:,} bytes decompressed) ===")
    print(f"  Format:           {FORMAT_LABELS.get(fmt, fmt)}")
    print(f"  Tracks:           {info['n_tracks']}")
    print(f"  Instruments:      {info['n_instruments']}")
    print(f"  Param2 (tempo?):  {info['meta_param2']}")
    print(f"  Param3 (loops?):  {info['meta_param3']}")
    print(f"  Track data:       0x{info['data_start']:04X}-0x{info['inst_offset']:04X} "
          f"({track_data_size:,} bytes)")
    print(f"  Instrument data:  0x{info['inst_offset']:04X}-0x{info['file_size']:04X} "
          f"({info['inst_size']:,} bytes)")
    if info['agd_params']:
        print(f"  AGD params:       0x{HERAD_DATA_START_OPL2:04X}-0x{HERAD_DATA_START_AGD:04X} "
              f"(32 bytes Tandy channel config)")

    # Per-track summary
    total_notes = 0
    if fmt == FMT_M32:
        print(f"\n  {'Track':>5}  {'Offset':>8}  {'Size':>6}  {'Notes':>5}  {'Chans':>5}  {'Events':>6}  {'Duration':>8}")
        print(f"  {'-----':>5}  {'--------':>8}  {'------':>6}  {'-----':>5}  {'-----':>5}  {'------':>6}  {'--------':>8}")
    else:
        print(f"\n  {'Track':>5}  {'Offset':>8}  {'Size':>6}  {'Notes':>5}  {'Events':>6}  {'Duration':>8}")
        print(f"  {'-----':>5}  {'--------':>8}  {'------':>6}  {'-----':>5}  {'------':>6}  {'--------':>8}")

    for track in info['tracks']:
        events = parse_track_events(track['data'], fmt)
        note_ons = sum(1 for _, etype, _ in events if etype == 'NOTE_ON')
        total_ticks = sum(delta for delta, _, _ in events)
        total_notes += note_ons

        if fmt == FMT_M32:
            # Count unique channels used
            channels = set()
            for _, etype, edata in events:
                if etype in ('NOTE_ON', 'NOTE_OFF', 'PROG_CHG', 'CONTROL', 'PITCH_BEND') and len(edata) >= 2:
                    channels.add(edata[-1])
            print(f"  {track['index']:5d}  0x{track['offset']:04X}  {track['size']:6,}  "
                  f"{note_ons:5d}  {len(channels):5d}  {len(events):6d}  {total_ticks:8,} ticks")
        else:
            print(f"  {track['index']:5d}  0x{track['offset']:04X}  {track['size']:6,}  "
                  f"{note_ons:5d}  {len(events):6d}  {total_ticks:8,} ticks")

    print(f"\n  Total notes: {total_notes}")


def show_tracks(filepath: str, data: bytes):
    """Show detailed track information."""
    fname = os.path.basename(filepath)
    info = parse_herad(data, filepath)
    fmt = info['format']

    print(f"=== {fname} Track Details ({FORMAT_LABELS.get(fmt, fmt)}) ===\n")

    for track in info['tracks']:
        events = parse_track_events(track['data'], fmt)

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

        # M32: show channels used
        if fmt == FMT_M32:
            channels = set()
            for _, etype, edata in events:
                if etype in ('NOTE_ON', 'NOTE_OFF') and len(edata) >= 3:
                    channels.add(edata[2])
            if channels:
                print(f"  Channels: {', '.join(str(c) for c in sorted(channels))}")
        print()


def show_events(filepath: str, data: bytes, track_idx: int):
    """Dump all events for a specific track."""
    fname = os.path.basename(filepath)
    info = parse_herad(data, filepath)
    fmt = info['format']

    if track_idx >= len(info['tracks']):
        print(f"Track {track_idx} out of range (0-{len(info['tracks'])-1})",
              file=sys.stderr)
        return

    track = info['tracks'][track_idx]
    events = parse_track_events(track['data'], fmt)

    print(f"=== {fname} Track {track_idx} Events ({FORMAT_LABELS.get(fmt, fmt)}) ===")
    print(f"  Offset: 0x{track['offset']:04X}, Size: {track['size']:,} bytes")
    print(f"  Events: {len(events)}\n")

    print(f"  {'#':>4}  {'Delta':>7}  {'Abs':>9}  {'Type':>12}  Details")
    print(f"  {'----':>4}  {'-------':>7}  {'---------':>9}  {'------------':>12}  -------")

    abs_time = 0
    for i, (delta, etype, edata) in enumerate(events):
        abs_time += delta
        detail = ""
        ch_str = ""

        if fmt == FMT_M32 and len(edata) >= 2 and etype not in ('VOICE', 'UNKNOWN'):
            ch_str = f" ch={edata[-1]}"

        if etype == 'NOTE_ON':
            nn = note_name(edata[0])
            detail = f"note={nn} ({edata[0]})  vel={edata[1]}{ch_str}"
        elif etype == 'NOTE_OFF':
            nn = note_name(edata[0])
            detail = f"note={nn} ({edata[0]})  vel={edata[1]}{ch_str}"
        elif etype == 'PROG_CHG':
            detail = f"instrument={edata[0]}{ch_str}"
        elif etype == 'CONTROL':
            detail = f"cc=0x{edata[0]:02X}  value={edata[1]}{ch_str}"
        elif etype == 'PITCH_BEND':
            val = edata[0] | (edata[1] << 7)
            detail = f"bend={val}{ch_str}"
        elif etype == 'AFTERTOUCH':
            detail = f"pressure={edata[0]}{ch_str}"
        elif etype == 'VOICE':
            if edata[0] == 0xFF:
                detail = "voice=0xFF (sync/default)"
            else:
                detail = f"voice=0x{edata[0]:02X}"

        print(f"  {i:4d}  {delta:7d}  {abs_time:9d}  {etype:>12}  {detail}")

        if i >= 999:
            remaining = len(events) - i - 1
            if remaining > 0:
                print(f"  ... ({remaining} more events)")
            break


def show_stats(filepaths: list):
    """Show summary statistics for multiple HERAD files."""
    print(f"{'File':<18} {'Format':<6} {'Size':>7}  {'Tracks':>6}  {'Instr':>5}  "
          f"{'Notes':>6}  {'P2':>4}  {'P3':>3}")
    print('-' * 72)

    for filepath in filepaths:
        raw = open(filepath, 'rb').read()
        try:
            data = hsq_decompress(raw)
        except Exception:
            continue

        if not is_herad_file(data, filepath):
            continue

        fname = os.path.basename(filepath)
        info = parse_herad(data, filepath)
        fmt = info['format']

        total_notes = 0
        for track in info['tracks']:
            events = parse_track_events(track['data'], fmt)
            total_notes += sum(1 for _, etype, _ in events if etype == 'NOTE_ON')

        fmt_short = {'OPL2': 'OPL2', 'AGD': 'AGD', 'M32': 'M32'}.get(fmt, fmt)
        print(f"{fname:<18} {fmt_short:<6} {info['file_size']:>7,}  {info['n_tracks']:>6}  "
              f"{info['n_instruments']:>5}  {total_notes:>6}  "
              f"{info['meta_param2']:>4}  {info['meta_param3']:>3}")


# =============================================================================
# MIDI EXPORT
# =============================================================================

def write_midi_vlq(value: int) -> bytes:
    """Encode a value as MIDI variable-length quantity."""
    if value < 0:
        value = 0
    buf = [value & 0x7F]
    value >>= 7
    while value > 0:
        buf.append(0x80 | (value & 0x7F))
        value >>= 7
    buf.reverse()
    return bytes(buf)


def export_midi(filepath: str, data: bytes, outpath: str, ticks_per_quarter: int = 120):
    """Convert HERAD music to Standard MIDI File (format 1).

    For OPL2/AGD: maps HERAD tracks to MIDI channels 0-8.
    For M32: preserves original channel assignments from the single track.
    """
    info = parse_herad(data, filepath)
    fmt = info['format']

    # MIDI header: format 1, N tracks, ticks per quarter note
    n_midi_tracks = info['n_tracks']
    header = b'MThd' + struct.pack('>IHhH', 6, 1, n_midi_tracks, ticks_per_quarter)

    tracks_data = []

    for ti, track in enumerate(info['tracks']):
        events = parse_track_events(track['data'], fmt)

        midi_events = bytearray()

        for delta, etype, edata in events:
            vlq = write_midi_vlq(delta)

            if fmt == FMT_M32:
                # M32: channel is already in edata
                ch = edata[-1] if len(edata) >= 3 else edata[-1] if len(edata) >= 2 else ti

                if etype == 'NOTE_ON':
                    note = min(edata[0], 127)
                    vel = min(edata[1], 127) if edata[1] > 0 else 64
                    midi_events.extend(vlq)
                    midi_events.extend(bytes([0x90 | ch, note, vel]))
                elif etype == 'NOTE_OFF':
                    note = min(edata[0], 127)
                    midi_events.extend(vlq)
                    midi_events.extend(bytes([0x80 | ch, note, 64]))
                elif etype == 'PROG_CHG':
                    prog = min(edata[0], 127)
                    midi_events.extend(vlq)
                    midi_events.extend(bytes([0xC0 | ch, prog]))
                elif etype == 'CONTROL':
                    cc = min(edata[0], 127)
                    val = min(edata[1], 127)
                    midi_events.extend(vlq)
                    midi_events.extend(bytes([0xB0 | ch, cc, val]))
                elif etype == 'PITCH_BEND':
                    midi_events.extend(vlq)
                    midi_events.extend(bytes([0xE0 | ch, edata[0] & 0x7F, edata[1] & 0x7F]))
            else:
                # OPL2/AGD: assign channel from track index
                channel = ti if ti < 16 else 15

                if etype == 'NOTE_ON':
                    note = min(edata[0], 127)
                    vel = min(edata[1], 127) if edata[1] > 0 else 64
                    midi_events.extend(vlq)
                    midi_events.extend(bytes([0x90 | channel, note, vel]))
                elif etype == 'NOTE_OFF':
                    note = min(edata[0], 127)
                    midi_events.extend(vlq)
                    midi_events.extend(bytes([0x80 | channel, note, 64]))
                elif etype == 'PROG_CHG':
                    prog = min(edata[0], 127)
                    midi_events.extend(vlq)
                    midi_events.extend(bytes([0xC0 | channel, prog]))
                elif etype == 'CONTROL':
                    param = min(edata[0], 127)
                    value = min(edata[1], 127)
                    midi_events.extend(vlq)
                    midi_events.extend(bytes([0xB0 | channel, param, value]))
                elif etype == 'VOICE':
                    if delta > 0:
                        midi_events.extend(vlq)
                        midi_events.extend(bytes([0xB0 | channel, 0x7B, 0]))

        # End of Track meta event
        midi_events.extend(b'\x00\xFF\x2F\x00')

        track_chunk = b'MTrk' + struct.pack('>I', len(midi_events)) + bytes(midi_events)
        tracks_data.append(track_chunk)

    midi_data = header + b''.join(tracks_data)

    with open(outpath, 'wb') as f:
        f.write(midi_data)

    fname = os.path.basename(filepath)
    fmt_label = FORMAT_LABELS.get(fmt, fmt)
    print(f"Exported {fname} ({fmt_label}) -> {outpath} ({len(midi_data):,} bytes, "
          f"{n_midi_tracks} tracks, {ticks_per_quarter} TPQ)")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 HERAD Music Format Decoder (HSQ/AGD/M32)',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('files', nargs='+', help='HERAD music file(s) (HSQ, AGD, or M32)')
    p.add_argument('--raw', action='store_true',
                   help='Input is already decompressed')
    p.add_argument('--tracks', action='store_true',
                   help='Show detailed track information')
    p.add_argument('--events', type=int, default=None, metavar='N',
                   help='Dump events for track N')
    p.add_argument('--stats', action='store_true',
                   help='Show summary statistics for all files')
    p.add_argument('--midi', type=str, default=None, metavar='DIR',
                   help='Export to MIDI files in DIR')
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

        if not is_herad_file(data, filepath):
            sig = struct.unpack_from('<H', data, 2)[0] if len(data) >= 4 else 0
            print(f"Not a HERAD file: {filepath} (signature=0x{sig:04X})",
                  file=sys.stderr)
            continue

        data = bytes(data)

        if args.midi:
            os.makedirs(args.midi, exist_ok=True)
            base = os.path.splitext(os.path.basename(filepath))[0]
            ext = os.path.splitext(filepath)[1].lower().replace('.', '_')
            outpath = os.path.join(args.midi, f"{base}{ext}.mid")
            export_midi(filepath, data, outpath)
        elif args.events is not None:
            show_events(filepath, data, args.events)
        elif args.tracks:
            show_tracks(filepath, data)
        else:
            show_file(filepath, data)

        print()

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
