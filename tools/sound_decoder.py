#!/usr/bin/env python3
"""
Dune 1992 Sound File Decoder

Decodes sound effects from HSQ-compressed Creative Voice File (VOC) format.
The game uses 6 sound effect files (SN1-SN4, SN6, SNA) containing Sound
Blaster digitized audio.

VOC file structure:
  Header (26 bytes):
    "Creative Voice File\x1A" (20 bytes)
    uint16 LE  header_size (always 0x001A = 26)
    uint16 LE  version (typically 0x010A = 1.10)
    uint16 LE  version_check (0x1129 + version)

  Data blocks (after header):
    Block type 0x01: Sound data
      uint8    type (0x01)
      uint24   length (3 bytes LE, includes sr+codec bytes)
      uint8    sample_rate_byte → rate = 1000000/(256-byte)
      uint8    codec (0x00 = 8-bit unsigned PCM)
      bytes    sample data (length-2 bytes)
    Block type 0x06: Repeat marker
    Block type 0x07: End repeat
    Block type 0x00: Terminator

Sound effects:
  SN1.HSQ - Worm sound / sandstorm
  SN2.HSQ - Ornithopter engine
  SN3.HSQ - Spice harvester
  SN4.HSQ - Short effect (click/beep)
  SN6.HSQ - Complex multi-part effect
  SNA.HSQ - Ambient sound

Usage:
  python3 sound_decoder.py gamedata/SN*.HSQ           # Analyze all sound files
  python3 sound_decoder.py gamedata/SN1.HSQ --wav DIR  # Export to WAV
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress

VOC_MAGIC = b'Creative Voice File\x1a'
VOC_HEADER_SIZE = 26


def parse_voc(data: bytes) -> dict:
    """Parse Creative Voice File structure."""
    if len(data) < VOC_HEADER_SIZE or data[:20] != VOC_MAGIC:
        raise ValueError("Not a VOC file")

    header_size = struct.unpack_from('<H', data, 20)[0]
    version = struct.unpack_from('<H', data, 22)[0]
    ver_check = struct.unpack_from('<H', data, 24)[0]

    blocks = []
    pos = header_size
    total_samples = 0
    sample_rate = 0

    while pos < len(data):
        block_type = data[pos]
        pos += 1

        if block_type == 0x00:
            # Terminator
            blocks.append({'type': 'end', 'offset': pos - 1})
            break

        if pos + 2 >= len(data):
            break

        # Block length (24-bit LE)
        block_len = data[pos] | (data[pos + 1] << 8) | (data[pos + 2] << 16)
        pos += 3

        if block_type == 0x01:
            # Sound data block
            if block_len < 2:
                pos += block_len
                continue
            sr_byte = data[pos]
            codec = data[pos + 1]
            rate = 1000000 // (256 - sr_byte) if sr_byte < 256 else 0
            n_samples = block_len - 2

            if sample_rate == 0:
                sample_rate = rate

            blocks.append({
                'type': 'sound',
                'offset': pos - 4,
                'sr_byte': sr_byte,
                'sample_rate': rate,
                'codec': codec,
                'n_samples': n_samples,
                'data_offset': pos + 2,
            })
            total_samples += n_samples
            pos += block_len

        elif block_type == 0x06:
            # Repeat start
            repeat_count = struct.unpack_from('<H', data, pos)[0] if block_len >= 2 else 0
            blocks.append({
                'type': 'repeat_start',
                'offset': pos - 4,
                'count': repeat_count,
            })
            pos += block_len

        elif block_type == 0x07:
            # End repeat
            blocks.append({'type': 'repeat_end', 'offset': pos - 4})
            pos += block_len

        elif block_type == 0x03:
            # Silence
            silence_len = struct.unpack_from('<H', data, pos)[0] if block_len >= 2 else 0
            sr_byte = data[pos + 2] if block_len >= 3 else 0
            rate = 1000000 // (256 - sr_byte) if sr_byte < 256 else 0
            blocks.append({
                'type': 'silence',
                'offset': pos - 4,
                'n_samples': silence_len + 1,
                'sample_rate': rate,
            })
            total_samples += silence_len + 1
            pos += block_len

        else:
            # Unknown block type
            blocks.append({'type': f'unknown_{block_type:02X}', 'offset': pos - 4})
            pos += block_len

    duration = total_samples / sample_rate if sample_rate > 0 else 0

    return {
        'file_size': len(data),
        'version': f"{version >> 8}.{version & 0xFF}",
        'header_size': header_size,
        'blocks': blocks,
        'sample_rate': sample_rate,
        'total_samples': total_samples,
        'duration': duration,
    }


def show_file(filepath: str, data: bytes):
    """Analyze a VOC sound file."""
    fname = os.path.basename(filepath)
    info = parse_voc(data)

    print(f"=== {fname} ({info['file_size']:,} bytes decompressed) ===")
    print(f"  VOC version:   {info['version']}")
    print(f"  Sample rate:   {info['sample_rate']:,} Hz")
    print(f"  Total samples: {info['total_samples']:,}")
    print(f"  Duration:      {info['duration']:.2f}s")

    sound_blocks = [b for b in info['blocks'] if b['type'] == 'sound']
    other_blocks = [b for b in info['blocks'] if b['type'] not in ('sound', 'end')]

    print(f"  Sound blocks:  {len(sound_blocks)}")
    if other_blocks:
        for b in other_blocks:
            if b['type'] == 'repeat_start':
                print(f"  Repeat:        {b['count']} times")
            elif b['type'] == 'silence':
                print(f"  Silence:       {b['n_samples']} samples")
            else:
                print(f"  {b['type']}")

    if len(sound_blocks) > 1:
        print(f"\n  {'Block':>5}  {'Offset':>8}  {'Samples':>8}  {'Rate':>6}  {'Codec':>5}")
        print(f"  {'-----':>5}  {'--------':>8}  {'--------':>8}  {'------':>6}  {'-----':>5}")
        for i, b in enumerate(sound_blocks):
            codec_name = 'PCM8' if b['codec'] == 0 else f'0x{b["codec"]:02X}'
            print(f"  {i:5d}  0x{b['offset']:04X}  {b['n_samples']:8,}  "
                  f"{b['sample_rate']:6,}  {codec_name}")


def export_wav(filepath: str, data: bytes, outdir: str):
    """Export VOC sound data as WAV file."""
    fname = os.path.basename(filepath)
    base = os.path.splitext(fname)[0]
    info = parse_voc(data)

    # Collect all sound data
    samples = bytearray()
    for block in info['blocks']:
        if block['type'] == 'sound':
            start = block['data_offset']
            end = start + block['n_samples']
            samples.extend(data[start:end])
        elif block['type'] == 'silence':
            samples.extend(bytes([0x80]) * block['n_samples'])

    if not samples:
        print(f"No audio data in {fname}", file=sys.stderr)
        return

    sr = info['sample_rate']
    outpath = os.path.join(outdir, f"{base}.wav")

    # Write WAV header (PCM 8-bit unsigned mono)
    data_size = len(samples)
    with open(outpath, 'wb') as f:
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + data_size))  # file size - 8
        f.write(b'WAVE')
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))          # chunk size
        f.write(struct.pack('<H', 1))           # PCM format
        f.write(struct.pack('<H', 1))           # mono
        f.write(struct.pack('<I', sr))          # sample rate
        f.write(struct.pack('<I', sr))          # byte rate (sr * 1 * 1)
        f.write(struct.pack('<H', 1))           # block align
        f.write(struct.pack('<H', 8))           # bits per sample
        f.write(b'data')
        f.write(struct.pack('<I', data_size))
        f.write(bytes(samples))

    print(f"Exported {fname} → {outpath} ({data_size:,} bytes, "
          f"{sr:,} Hz, {info['duration']:.2f}s)")


def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 Sound File Decoder (VOC format)',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('files', nargs='+', help='Sound HSQ file(s)')
    p.add_argument('--raw', action='store_true',
                   help='Input is already decompressed')
    p.add_argument('--wav', type=str, default=None, metavar='DIR',
                   help='Export to WAV files in DIR')
    args = p.parse_args()

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

        # Verify VOC signature
        if len(data) < VOC_HEADER_SIZE or data[:20] != VOC_MAGIC:
            print(f"Not a VOC file: {filepath}", file=sys.stderr)
            continue

        data = bytes(data)

        if args.wav:
            os.makedirs(args.wav, exist_ok=True)
            export_wav(filepath, data, args.wav)
        else:
            show_file(filepath, data)

        print()

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
