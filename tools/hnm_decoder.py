#!/usr/bin/env python3
"""
Dune 1992 HNM Video File Analyzer

Analyzes Cryo Interactive HNM video files used for cutscenes and animations.

HNM file structure (from OpenRakis HNMExtractor.cpp):
  Chunk-based format. Each chunk starts with uint16 LE chunk_size.

  First chunk (index 0):
    - VGA palette data (same chunk format as sprite files: start, count, RGB)
    - Terminated by 0xFFFF
    - Followed by frame offset table

  Subsequent chunks (frames):
    - Sub-chunks with 2-byte tags:
      'sd' = sound data
      'pl' = palette update
      'pt' = unknown
      'kl' = unknown
      Other = video frame: bits[8:0]=width, byte[2]&0xFF=height, byte[3]=mode

  Video frame decompression:
    - HSQ-style LZ77 decompression (checksum 0xAB = 171)
    - AD decompression (checksum 0xAD = 173): codebook-based with RLE

  Resolution: typically 320×200 (video area 320×152 + status bar)
"""

import argparse
import os
import struct
import sys


def analyze_hnm(filepath):
    """Analyze an HNM file and report its structure."""
    data = open(filepath, 'rb').read()
    fname = os.path.basename(filepath)
    fsize = len(data)

    print(f"File: {fname} ({fsize:,} bytes)")

    # Parse chunks
    pos = 0
    chunk_idx = 0
    frames = 0
    sound_chunks = 0
    palette_chunks = 0
    total_sound_bytes = 0

    while pos < fsize:
        if pos + 2 > fsize:
            break

        chunk_size = struct.unpack_from('<H', data, pos)[0]
        if chunk_size == 0:
            break

        chunk_end = pos + chunk_size
        if chunk_end > fsize:
            break

        if chunk_idx == 0:
            # First chunk: palette + offset table
            # Count palette colors
            pal_pos = pos + 2
            pal_colors = 0
            while pal_pos + 1 < chunk_end:
                start = data[pal_pos]
                count = data[pal_pos + 1]
                if start == 0xFF and count == 0xFF:
                    pal_pos += 2
                    break
                if count == 0:
                    count = 256
                pal_colors += count
                pal_pos += 2 + count * 3

            print(f"  Chunk 0 (header): {chunk_size} bytes, {pal_colors} palette colors")
        else:
            # Parse sub-chunks
            sub_pos = pos + 2
            while sub_pos + 4 <= chunk_end:
                tag = data[sub_pos:sub_pos + 2]
                sub_size = struct.unpack_from('<H', data, sub_pos + 2)[0]

                if tag == b'sd':
                    sound_chunks += 1
                    total_sound_bytes += sub_size - 4
                elif tag == b'pl':
                    palette_chunks += 1
                elif tag == b'pt' or tag == b'kl':
                    pass
                else:
                    # Video frame
                    w = struct.unpack_from('<H', data, sub_pos)[0] & 0x1FF
                    h = data[sub_pos + 2] & 0xFF
                    if w > 0 and h > 0:
                        frames += 1
                    break  # only one frame per chunk

                if sub_size == 0:
                    break
                sub_pos += sub_size

        pos = chunk_end
        chunk_idx += 1

    print(f"  Total chunks: {chunk_idx}")
    print(f"  Video frames: {frames}")
    print(f"  Sound chunks: {sound_chunks} ({total_sound_bytes:,} bytes)")
    print(f"  Palette updates: {palette_chunks}")

    # Estimate duration (assuming ~15 fps for Dune HNM)
    if frames > 0:
        est_duration = frames / 15.0
        print(f"  Est. duration: {est_duration:.1f}s ({frames} frames @ ~15fps)")

    return chunk_idx, frames


def main():
    parser = argparse.ArgumentParser(
        description='Dune 1992 HNM Video File Analyzer')
    parser.add_argument('files', nargs='+', help='HNM video file(s)')
    parser.add_argument('--stats', action='store_true',
                        help='Show summary statistics for all files')
    args = parser.parse_args()

    if args.stats:
        print(f"{'File':<16} {'Size':>10}  {'Chunks':>6}  {'Frames':>6}")
        print('-' * 44)

    for filepath in args.files:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}", file=sys.stderr)
            continue

        if args.stats:
            data = open(filepath, 'rb').read()
            fname = os.path.basename(filepath)
            # Quick chunk count
            pos = 0
            chunks = 0
            frames = 0
            while pos < len(data):
                if pos + 2 > len(data):
                    break
                cs = struct.unpack_from('<H', data, pos)[0]
                if cs == 0:
                    break
                chunks += 1
                if chunks > 1:
                    # Check for video frame in chunk
                    sub_pos = pos + 2
                    if sub_pos + 4 <= pos + cs:
                        tag = data[sub_pos:sub_pos + 2]
                        if tag not in (b'sd', b'pl', b'pt', b'kl'):
                            w = struct.unpack_from('<H', data, sub_pos)[0] & 0x1FF
                            h = data[sub_pos + 2] & 0xFF
                            if w > 0 and h > 0:
                                frames += 1
                pos += cs

            print(f"{fname:<16} {len(data):>10,}  {chunks:>6}  {frames:>6}")
        else:
            analyze_hnm(filepath)
            print()

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
