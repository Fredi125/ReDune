#!/usr/bin/env python
"""
Dune 1992 HNM Video File Decoder

Decodes Cryo Interactive HNM (version 1) video files used for cutscenes.

HNM file structure:
  Chunk-based format. Each chunk starts with uint16 LE chunk_size.

  Chunk 0 (header):
    - uint16 LE: headerSize (total size of this chunk)
    - Palette blocks: series of (uint16 LE) entries:
        - 0xFFFF: end of palette data
        - 0x0100: skip 3 bytes (padding)
        - Other: low byte = start index, high byte = count (0 → 256)
                 followed by count × 3 bytes of 6-bit VGA RGB
    - After palette: skip 0xFF fill bytes
    - Frame offset table: uint32 LE values (relative to headerSize)
      Number of frames = (headerSize - table_pos) / 4 - 1

  Subsequent chunks (AV frames):
    - uint16 LE: avFrameSize
    - Sub-chunks (tagged):
        'pl' (0x6C70): palette update block
        'sd' (0x6473): sound data (8-bit unsigned PCM @ 11111 Hz)
        'mm' (0x6D6D): metadata (unused)
        Other: video frame (tag = first 2 bytes of 4-byte frame header)

  Video frame header (4 bytes):
    byte 0: width low 8 bits
    byte 1: bit 0 = width bit 8, bits 1-7 = flags
    byte 2: height
    byte 3: mode (0xFE=opaque, 0xFF=transparent)

  Video frame flags:
    0x02: HSQ-compressed data follows
    0x04: full frame (no x,y offset in decompressed data)
    0x80: PackBits-compressed rendering

  Decompression dispatch (6-byte header checksum):
    0xAB (171): HSQ/LZ77 codec (standard)
    0xAD (173): AD codec (codebook + RLE, advanced)

  References:
    - OpenRakis HNMExtractor.cpp (VAG, 2006)
    - madmoose/dune ScummVM video.cpp, hsq.h
    - OpenRakis graphics.cpp (blitGraphics, PackBits)

Usage:
  python hnm_decoder.py CRYO.HNM                    # Analyze structure
  python hnm_decoder.py gamedata/*.HNM --stats       # Summary table
  python hnm_decoder.py CRYO.HNM --extract frames/   # Extract frames as BMP
  python hnm_decoder.py CRYO.HNM --extract-sound out.wav  # Extract audio
  python hnm_decoder.py CRYO.HNM --palette            # Dump initial palette
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress


# =============================================================================
# PALETTE PARSING
# =============================================================================

def parse_palette_block(data: bytes, pos: int) -> tuple:
    """
    Parse VGA palette block(s) from HNM data.

    Format: series of uint16 LE entries until 0xFFFF terminator.
    Each entry: low byte = start palette index, high byte = count (0→256).
    Followed by count × 3 bytes of 6-bit VGA RGB values.
    Special: 0x0100 = skip 3 bytes.

    Returns:
        (palette_array_768_bytes, position_after_palette)
    """
    palette = bytearray(768)  # 256 × 3 RGB

    while pos + 1 < len(data):
        word = struct.unpack_from('<H', data, pos)[0]
        pos += 2

        if word == 0xFFFF:
            break

        if word == 0x0100:
            pos += 3  # skip padding
            continue

        start_idx = word & 0xFF
        count = (word >> 8) & 0xFF
        if count == 0:
            count = 256

        for i in range(count):
            if pos + 2 >= len(data):
                break
            idx = (start_idx + i) * 3
            if idx + 2 < len(palette):
                # 6-bit VGA → 8-bit: val << 2 | val >> 4
                r = data[pos]
                g = data[pos + 1]
                b = data[pos + 2]
                palette[idx] = (r << 2) | (r >> 4)
                palette[idx + 1] = (g << 2) | (g >> 4)
                palette[idx + 2] = (b << 2) | (b >> 4)
            pos += 3

    return bytes(palette), pos


# =============================================================================
# FRAME DECOMPRESSION
# =============================================================================

def decompress_frame_hsq(data: bytes) -> bytes:
    """
    Decompress an HSQ/LZ77 compressed video frame.

    The 6-byte header (ulen, zero, plen, salt) is identical to standard HSQ.
    Checksum of all 6 bytes == 0xAB.
    """
    return hsq_decompress(data)


def decompress_frame_ad(data: bytes) -> tuple:
    """
    Decompress an AD-codec video frame (codebook + RLE).

    AD header (6 bytes):
      uint16 LE: framesize (decompressed pixel data size)
      uint16 LE: codebooksize
      uint8:     flags
      uint8:     salt (checksum byte, sum == 0xAD)

    Returns:
        (pixel_data, x_offset, y_offset)
    """
    if len(data) < 6:
        return b'', 0, 0

    framesize = struct.unpack_from('<H', data, 0)[0]
    codebooksize = struct.unpack_from('<H', data, 2)[0]
    flags = data[4]

    pos = 6

    # Read x,y offset if not full frame
    if not (flags & 0x04):
        x = struct.unpack_from('<H', data, pos)[0]
        y = struct.unpack_from('<H', data, pos + 2)[0]
        pos += 4
    else:
        x, y = 0, 0

    # Unpack codebook
    colorbase = 0x80 if (flags & 0x40) else 0
    codebook = bytearray(codebooksize)
    cb_pos = 0
    flip = 0
    o_val = 0

    inp_pos = pos
    while cb_pos < codebooksize and inp_pos < len(data):
        tag = data[inp_pos]
        inp_pos += 1

        if tag & 0x80:
            if not flip:
                if inp_pos >= len(data):
                    break
                o_val = data[inp_pos]
                inp_pos += 1
                length = o_val >> 4
            else:
                length = o_val & 0x0F
            flip ^= 1

            ofs_val = (tag << 1) | (length & 1)
            length = (length >> 1) + 2

            for _ in range(length):
                if cb_pos >= codebooksize:
                    break
                src_idx = cb_pos - ofs_val - 1
                if 0 <= src_idx < cb_pos:
                    codebook[cb_pos] = codebook[src_idx]
                cb_pos += 1
        else:
            if tag:
                tag = (tag + colorbase) & 0xFF
            if cb_pos < codebooksize:
                codebook[cb_pos] = tag
            cb_pos += 1

    # Decode pixel data using codebook + bit stream
    output = bytearray(framesize)
    out_pos = 0
    temp_pos = 0
    flip2 = 0
    o_val2 = 0

    # Bit queue for AD codec
    queue = 0x8000

    def get_bit_ad():
        nonlocal queue, inp_pos
        if queue == 0x8000:
            if inp_pos + 1 >= len(data):
                return 0
            word = struct.unpack_from('<H', data, inp_pos)[0]
            inp_pos += 2
            queue = (word << 1) | 1
            return (word >> 15) & 1
        result = (queue >> 15) & 1
        if queue & 0x8000:
            queue = (queue << 1) | 0x8000
        else:
            queue = (queue << 1) & 0x7FFF
        return result

    if not (flags & 0x80):
        # Standard AD mode
        while out_pos < framesize and temp_pos < codebooksize:
            while not get_bit_ad():
                if temp_pos >= codebooksize or out_pos >= framesize:
                    break
                output[out_pos] = codebook[temp_pos]
                out_pos += 1
                temp_pos += 1

            if temp_pos >= codebooksize or out_pos >= framesize:
                break

            c = codebook[temp_pos]
            temp_pos += 1

            if not get_bit_ad():
                # Repeat 2×
                for _ in range(2):
                    if out_pos < framesize:
                        output[out_pos] = c
                        out_pos += 1
            elif not get_bit_ad():
                # Repeat 3×
                for _ in range(3):
                    if out_pos < framesize:
                        output[out_pos] = c
                        out_pos += 1
            elif not get_bit_ad():
                # Repeat 4×
                for _ in range(4):
                    if out_pos < framesize:
                        output[out_pos] = c
                        out_pos += 1
            else:
                # Long run
                if out_pos >= framesize:
                    break
                if not flip2:
                    if inp_pos >= len(data):
                        break
                    o_val2 = data[inp_pos]
                    inp_pos += 1
                    run_len = o_val2 >> 4
                else:
                    run_len = o_val2 & 0x0F
                flip2 ^= 1

                if run_len == 0:
                    if inp_pos >= len(data):
                        break
                    run_len = data[inp_pos] + 16
                    inp_pos += 1

                for _ in range(run_len + 4):
                    if out_pos < framesize:
                        output[out_pos] = c
                        out_pos += 1
    else:
        # Alternate AD mode (flags & 0x80)
        while out_pos < framesize and temp_pos < codebooksize:
            while not get_bit_ad():
                if temp_pos >= codebooksize or out_pos >= framesize:
                    break
                output[out_pos] = codebook[temp_pos]
                out_pos += 1
                temp_pos += 1

            if temp_pos >= codebooksize or out_pos >= framesize:
                break

            c = codebook[temp_pos]
            temp_pos += 1

            if not get_bit_ad():
                # Long run first in this mode
                if not flip2:
                    if inp_pos >= len(data):
                        break
                    o_val2 = data[inp_pos]
                    inp_pos += 1
                    run_len = o_val2 >> 4
                else:
                    run_len = o_val2 & 0x0F
                flip2 ^= 1

                if run_len == 0:
                    if inp_pos >= len(data):
                        break
                    run_len = data[inp_pos] + 16
                    inp_pos += 1

                for _ in range(run_len + 4):
                    if out_pos < framesize:
                        output[out_pos] = c
                        out_pos += 1
            elif not get_bit_ad():
                # Repeat 2×
                for _ in range(2):
                    if out_pos < framesize:
                        output[out_pos] = c
                        out_pos += 1
            elif not get_bit_ad():
                # Repeat 3×
                for _ in range(3):
                    if out_pos < framesize:
                        output[out_pos] = c
                        out_pos += 1
            else:
                if out_pos >= framesize:
                    break
                # Repeat 4×
                for _ in range(4):
                    if out_pos < framesize:
                        output[out_pos] = c
                        out_pos += 1

    return bytes(output[:framesize]), x, y


def get_frame_checksum(data: bytes) -> int:
    """Calculate 6-byte header checksum for frame compression detection."""
    if len(data) < 6:
        return 0
    return sum(data[:6]) & 0xFF


# =============================================================================
# FRAME RENDERING
# =============================================================================

def render_frame(pixel_data: bytes, framebuf: bytearray,
                 x_off: int, y_off: int, w: int, h: int,
                 flags: int, mode: int, src_offset: int = 0):
    """
    Render decoded pixel data onto 320×200 frame buffer.

    Modes:
      0xFE: opaque copy
      0xFF: transparent (pixel 0 = skip)

    Flags:
      0x80: PackBits compressed scanlines
    """
    if w == 0 or h == 0:
        return

    if flags & 0x80:
        # PackBits compressed rendering
        pos = src_offset
        for y in range(h):
            dst_base = 320 * (y + y_off) + x_off
            line_remain = w
            while line_remain > 0 and pos < len(pixel_data):
                cmd = pixel_data[pos]
                pos += 1
                if cmd & 0x80:
                    # RLE: repeat next byte (257 - cmd) times
                    count = 257 - cmd
                    if pos >= len(pixel_data):
                        break
                    value = pixel_data[pos]
                    pos += 1
                    for i in range(count):
                        if line_remain <= 0:
                            break
                        dst = dst_base + (w - line_remain)
                        if mode == 0xFF and value == 0:
                            pass  # transparent
                        elif 0 <= dst < 64000:
                            framebuf[dst] = value
                        line_remain -= 1
                else:
                    # Literal: copy (cmd + 1) bytes
                    count = cmd + 1
                    for i in range(count):
                        if line_remain <= 0 or pos >= len(pixel_data):
                            break
                        value = pixel_data[pos]
                        pos += 1
                        dst = dst_base + (w - line_remain)
                        if mode == 0xFF and value == 0:
                            pass  # transparent
                        elif 0 <= dst < 64000:
                            framebuf[dst] = value
                        line_remain -= 1
    else:
        # Uncompressed rendering
        pos = src_offset
        for y in range(h):
            for x in range(w):
                if pos >= len(pixel_data):
                    return
                value = pixel_data[pos]
                pos += 1
                dst = 320 * (y + y_off) + (x + x_off)
                if mode == 0xFF and value == 0:
                    continue  # transparent
                if 0 <= dst < 64000:
                    framebuf[dst] = value


# =============================================================================
# BMP EXPORT
# =============================================================================

def write_bmp(filepath: str, pixels: bytes, palette: bytes,
              width: int = 320, height: int = 200):
    """Write 8-bit indexed BMP file."""
    row_size = (width + 3) & ~3  # pad to 4-byte boundary
    pixel_data_size = row_size * height
    file_size = 54 + 1024 + pixel_data_size  # header + palette + pixels

    with open(filepath, 'wb') as f:
        # BMP file header (14 bytes)
        f.write(b'BM')
        f.write(struct.pack('<I', file_size))
        f.write(struct.pack('<HH', 0, 0))
        f.write(struct.pack('<I', 54 + 1024))

        # DIB header (40 bytes)
        f.write(struct.pack('<I', 40))
        f.write(struct.pack('<i', width))
        f.write(struct.pack('<i', -height))  # top-down
        f.write(struct.pack('<HH', 1, 8))
        f.write(struct.pack('<I', 0))  # no compression
        f.write(struct.pack('<I', pixel_data_size))
        f.write(struct.pack('<ii', 2835, 2835))  # 72 DPI
        f.write(struct.pack('<II', 256, 0))

        # Palette (256 × BGRA)
        for i in range(256):
            r = palette[i * 3] if i * 3 < len(palette) else 0
            g = palette[i * 3 + 1] if i * 3 + 1 < len(palette) else 0
            b = palette[i * 3 + 2] if i * 3 + 2 < len(palette) else 0
            f.write(struct.pack('BBBB', b, g, r, 0))

        # Pixel data (top-down, padded rows)
        for y in range(height):
            row_start = y * width
            row = pixels[row_start:row_start + width]
            if len(row) < width:
                row = row + b'\x00' * (width - len(row))
            if row_size > width:
                row = row + b'\x00' * (row_size - width)
            f.write(row)


# =============================================================================
# WAV EXPORT
# =============================================================================

def write_wav(filepath: str, audio_data: bytes, sample_rate: int = 11111):
    """Write 8-bit unsigned PCM WAV file."""
    data_size = len(audio_data)
    with open(filepath, 'wb') as f:
        # RIFF header
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + data_size))
        f.write(b'WAVE')
        # fmt chunk
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))
        f.write(struct.pack('<HH', 1, 1))  # PCM, mono
        f.write(struct.pack('<I', sample_rate))
        f.write(struct.pack('<I', sample_rate))  # byte rate
        f.write(struct.pack('<HH', 1, 8))  # block align, bits
        # data chunk
        f.write(b'data')
        f.write(struct.pack('<I', data_size))
        f.write(audio_data)


# =============================================================================
# HNM FILE PARSER
# =============================================================================

class HnmFile:
    """Parser for Dune HNM video files."""

    def __init__(self, data: bytes):
        self.data = data
        self.palette = bytes(768)
        self.frame_offsets = []
        self.header_size = 0
        self.frame_count = 0
        self.chunks = []
        self._parse()

    def _parse(self):
        """Parse the HNM file structure."""
        if len(self.data) < 4:
            return

        # Chunk 0: header
        self.header_size = struct.unpack_from('<H', self.data, 0)[0]
        if self.header_size > len(self.data):
            return

        # Parse palette
        self.palette, pal_end = parse_palette_block(self.data, 2)

        # Skip 0xFF fill bytes after palette
        pos = pal_end
        while pos < self.header_size and self.data[pos] == 0xFF:
            pos += 1

        # Parse frame offset table
        table_size = self.header_size - pos
        if table_size >= 4:
            n_entries = table_size // 4
            for i in range(n_entries):
                off = struct.unpack_from('<I', self.data, pos)[0]
                self.frame_offsets.append(off)
                pos += 4

        if len(self.frame_offsets) > 1:
            self.frame_count = len(self.frame_offsets) - 1
        else:
            self.frame_count = 0

        # Parse AV frame chunks
        chunk_pos = self.header_size
        for frame_idx in range(self.frame_count):
            expected_pos = self.frame_offsets[frame_idx] + self.header_size
            if expected_pos >= len(self.data):
                break

            av_size = struct.unpack_from('<H', self.data, expected_pos)[0]
            self.chunks.append({
                'offset': expected_pos,
                'size': av_size,
                'frame_idx': frame_idx,
            })

    def get_frame_info(self, frame_idx: int) -> dict:
        """Get detailed info about a specific frame."""
        if frame_idx >= self.frame_count or frame_idx >= len(self.frame_offsets) - 1:
            return {}

        frame_start = self.frame_offsets[frame_idx] + self.header_size
        frame_end = self.frame_offsets[frame_idx + 1] + self.header_size

        if frame_start + 2 > len(self.data):
            return {}

        av_size = struct.unpack_from('<H', self.data, frame_start)[0]
        pos = frame_start + 2

        info = {
            'offset': frame_start,
            'av_size': av_size,
            'sound': False,
            'palette': False,
            'video': False,
            'width': 0,
            'height': 0,
            'flags': 0,
            'mode': 0,
            'codec': None,
        }

        while pos + 4 <= frame_end and pos + 4 <= len(self.data):
            tag = struct.unpack_from('<H', self.data, pos)[0]

            if tag == 0x6C70:  # 'pl'
                info['palette'] = True
                sub_size = struct.unpack_from('<H', self.data, pos + 2)[0]
                if sub_size == 0:
                    break
                pos += sub_size
            elif tag == 0x6473:  # 'sd'
                info['sound'] = True
                sub_size = struct.unpack_from('<H', self.data, pos + 2)[0]
                if sub_size == 0:
                    break
                pos += sub_size
            elif tag == 0x6D6D:  # 'mm'
                sub_size = struct.unpack_from('<H', self.data, pos + 2)[0]
                if sub_size == 0:
                    break
                pos += sub_size
            else:
                # Video frame header
                b0 = self.data[pos] if pos < len(self.data) else 0
                b1 = self.data[pos + 1] if pos + 1 < len(self.data) else 0
                b2 = self.data[pos + 2] if pos + 2 < len(self.data) else 0
                b3 = self.data[pos + 3] if pos + 3 < len(self.data) else 0

                w = ((b1 & 0x01) << 8) | b0
                flags = b1 & 0xFE
                h = b2
                mode = b3

                info['video'] = True
                info['width'] = w
                info['height'] = h
                info['flags'] = flags
                info['mode'] = mode

                # Check codec type
                data_pos = pos + 4
                if w > 0 and h > 0 and (flags & 0x02) and data_pos + 6 <= len(self.data):
                    checksum = get_frame_checksum(self.data[data_pos:data_pos + 6])
                    if checksum == 0xAB:
                        info['codec'] = 'LZ'
                    elif checksum == 0xAD:
                        info['codec'] = 'AD'
                    else:
                        info['codec'] = f'0x{checksum:02X}'
                elif w > 0 and h > 0 and not (flags & 0x02):
                    info['codec'] = 'raw'

                break

        return info

    def decode_frame(self, frame_idx: int, framebuf: bytearray,
                     palette: bytearray) -> bool:
        """
        Decode a single frame and render to frame buffer.

        Updates palette in-place if the frame contains palette data.
        Returns True if a video frame was decoded.
        """
        if frame_idx >= self.frame_count or frame_idx >= len(self.frame_offsets) - 1:
            return False

        frame_start = self.frame_offsets[frame_idx] + self.header_size
        frame_end = self.frame_offsets[frame_idx + 1] + self.header_size

        if frame_start + 2 > len(self.data):
            return False

        pos = frame_start + 2  # skip avFrameSize

        had_video = False

        while pos + 4 <= frame_end and pos + 4 <= len(self.data):
            tag = struct.unpack_from('<H', self.data, pos)[0]

            if tag == 0x6C70:  # 'pl' — palette update
                sub_size = struct.unpack_from('<H', self.data, pos + 2)[0]
                new_pal, _ = parse_palette_block(self.data, pos + 4)
                # Merge non-zero entries into palette
                for i in range(256):
                    r, g, b = new_pal[i*3], new_pal[i*3+1], new_pal[i*3+2]
                    if r != 0 or g != 0 or b != 0:
                        palette[i*3] = r
                        palette[i*3+1] = g
                        palette[i*3+2] = b
                if sub_size == 0:
                    break
                pos += sub_size

            elif tag == 0x6473:  # 'sd' — sound data (skip)
                sub_size = struct.unpack_from('<H', self.data, pos + 2)[0]
                if sub_size == 0:
                    break
                pos += sub_size

            elif tag == 0x6D6D:  # 'mm' — metadata (skip)
                sub_size = struct.unpack_from('<H', self.data, pos + 2)[0]
                if sub_size == 0:
                    break
                pos += sub_size

            else:
                # Video frame
                b0 = self.data[pos]
                b1 = self.data[pos + 1]
                b2 = self.data[pos + 2]
                b3 = self.data[pos + 3]

                w = ((b1 & 0x01) << 8) | b0
                flags = b1 & 0xFE
                h = b2
                mode = b3
                data_pos = pos + 4

                if w == 0 or h == 0:
                    break

                remaining = frame_end - data_pos

                if flags & 0x02:
                    # Compressed frame
                    frame_data = self.data[data_pos:data_pos + remaining]
                    checksum = get_frame_checksum(frame_data)

                    if checksum == 0xAB:
                        # HSQ/LZ77
                        try:
                            decoded = decompress_frame_hsq(frame_data)
                        except Exception:
                            break
                    elif checksum == 0xAD:
                        # AD codec
                        try:
                            decoded, ad_x, ad_y = decompress_frame_ad(frame_data)
                        except Exception:
                            break
                        # AD codec handles its own x,y
                        render_frame(decoded, framebuf, ad_x, ad_y, w, h,
                                     flags, mode)
                        had_video = True
                        break
                    else:
                        break

                    # Standard HSQ decoded frame
                    if flags & 0x04:
                        # Full frame, no offset
                        render_frame(decoded, framebuf, 0, 0, w, h,
                                     flags, mode)
                    else:
                        # Frame has x,y offset in first 4 bytes
                        if len(decoded) >= 4:
                            x_off = struct.unpack_from('<H', decoded, 0)[0]
                            y_off = struct.unpack_from('<H', decoded, 2)[0]
                            render_frame(decoded, framebuf, x_off, y_off,
                                         w, h, flags, mode, src_offset=4)
                else:
                    # Uncompressed frame
                    raw_data = self.data[data_pos:data_pos + remaining]

                    if flags & 0x04:
                        render_frame(raw_data, framebuf, 0, 0, w, h,
                                     flags, mode)
                    else:
                        if len(raw_data) >= 4:
                            x_off = struct.unpack_from('<H', raw_data, 0)[0]
                            y_off = struct.unpack_from('<H', raw_data, 2)[0]
                            render_frame(raw_data, framebuf, x_off, y_off,
                                         w, h, flags, mode, src_offset=4)

                had_video = True
                break

        return had_video

    def extract_sound(self) -> bytes:
        """Extract all sound data from the HNM file."""
        audio = bytearray()

        for frame_idx in range(self.frame_count):
            frame_start = self.frame_offsets[frame_idx] + self.header_size
            frame_end = self.frame_offsets[frame_idx + 1] + self.header_size

            if frame_start + 2 > len(self.data):
                break

            pos = frame_start + 2

            while pos + 4 <= frame_end and pos + 4 <= len(self.data):
                tag = struct.unpack_from('<H', self.data, pos)[0]
                sub_size = struct.unpack_from('<H', self.data, pos + 2)[0]

                if tag == 0x6473:  # 'sd'
                    sound_bytes = sub_size - 4
                    if sound_bytes > 0 and pos + 4 + sound_bytes <= len(self.data):
                        audio.extend(self.data[pos + 4:pos + 4 + sound_bytes])

                if sub_size == 0 or tag not in (0x6C70, 0x6473, 0x6D6D):
                    break
                pos += sub_size

        return bytes(audio)


# =============================================================================
# ANALYSIS AND OUTPUT
# =============================================================================

def analyze_hnm(filepath: str):
    """Analyze an HNM file and report its structure."""
    data = open(filepath, 'rb').read()
    fname = os.path.basename(filepath)
    hnm = HnmFile(data)

    print(f"File: {fname} ({len(data):,} bytes)")
    print(f"  Header size: {hnm.header_size} bytes")
    print(f"  Frame count: {hnm.frame_count}")

    # Analyze frames
    codecs = {'LZ': 0, 'AD': 0, 'raw': 0}
    sound_frames = 0
    palette_frames = 0
    resolutions = set()
    modes = set()

    for i in range(min(hnm.frame_count, 5000)):
        info = hnm.get_frame_info(i)
        if not info:
            break
        if info.get('sound'):
            sound_frames += 1
        if info.get('palette'):
            palette_frames += 1
        if info.get('video'):
            w, h = info['width'], info['height']
            if w > 0 and h > 0:
                resolutions.add(f"{w}x{h}")
                modes.add(info['mode'])
            codec = info.get('codec')
            if codec and codec in codecs:
                codecs[codec] += 1

    print(f"  Resolutions: {', '.join(sorted(resolutions)) if resolutions else 'none'}")
    print(f"  Modes: {', '.join(f'0x{m:02X}' for m in sorted(modes)) if modes else 'none'}")
    print(f"  Codecs: LZ={codecs['LZ']} AD={codecs['AD']} raw={codecs['raw']}")
    print(f"  Sound frames: {sound_frames}")
    print(f"  Palette updates: {palette_frames}")

    # Audio info
    audio = hnm.extract_sound()
    if audio:
        duration = len(audio) / 11111.0
        print(f"  Audio: {len(audio):,} bytes ({duration:.1f}s @ 11111 Hz)")

    # Video duration estimate
    if hnm.frame_count > 0:
        # Frame rate varies; audio-based estimate is more accurate
        if audio:
            fps = hnm.frame_count / duration if duration > 0 else 0
            print(f"  Est. FPS: {fps:.1f}")
        else:
            print(f"  Est. duration: {hnm.frame_count / 15.0:.1f}s (assuming 15 fps)")

    return hnm


def extract_frames(hnm: HnmFile, outdir: str, max_frames: int = 0):
    """Extract video frames as BMP images."""
    os.makedirs(outdir, exist_ok=True)

    framebuf = bytearray(64000)  # 320×200
    palette = bytearray(hnm.palette)

    count = hnm.frame_count
    if max_frames > 0:
        count = min(count, max_frames)

    extracted = 0
    errors = 0

    for i in range(count):
        try:
            had_video = hnm.decode_frame(i, framebuf, palette)
            if had_video or i == 0:
                bmp_path = os.path.join(outdir, f"frame_{i:04d}.bmp")
                write_bmp(bmp_path, bytes(framebuf), bytes(palette))
                extracted += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Frame {i}: error: {e}", file=sys.stderr)

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{count} frames ({extracted} extracted)")

    print(f"  Extracted {extracted} frames to {outdir}/ ({errors} errors)")


def show_palette(hnm: HnmFile):
    """Display the initial palette."""
    pal = hnm.palette
    print("Initial palette (256 colors, RGB 8-bit):")
    for i in range(256):
        r, g, b = pal[i*3], pal[i*3+1], pal[i*3+2]
        if r != 0 or g != 0 or b != 0:
            print(f"  [{i:3d}] R={r:3d} G={g:3d} B={b:3d}  "
                  f"#{r:02X}{g:02X}{b:02X}")


def main():
    parser = argparse.ArgumentParser(
        description='Dune 1992 HNM Video File Decoder')
    parser.add_argument('files', nargs='+', help='HNM video file(s)')
    parser.add_argument('--stats', action='store_true',
                        help='Summary table for all files')
    parser.add_argument('--extract', metavar='OUTDIR',
                        help='Extract frames as BMP to directory')
    parser.add_argument('--max-frames', type=int, default=0,
                        help='Max frames to extract (0=all)')
    parser.add_argument('--extract-sound', metavar='WAVFILE',
                        help='Extract audio to WAV file')
    parser.add_argument('--palette', action='store_true',
                        help='Dump initial palette')
    parser.add_argument('--frame-info', type=int, metavar='N',
                        help='Show detailed info for frame N')
    args = parser.parse_args()

    if args.stats:
        print(f"{'File':<16} {'Size':>10}  {'Frames':>6}  {'Audio':>8}  "
              f"{'Resolution':<10}  {'Codecs'}")
        print('-' * 72)

        for filepath in args.files:
            if not os.path.exists(filepath):
                continue
            data = open(filepath, 'rb').read()
            fname = os.path.basename(filepath)
            hnm = HnmFile(data)

            # Quick scan for resolution and codecs
            res = set()
            codec_set = set()
            for i in range(min(hnm.frame_count, 10)):
                info = hnm.get_frame_info(i)
                if info and info.get('video'):
                    w, h = info['width'], info['height']
                    if w > 0 and h > 0:
                        res.add(f"{w}x{h}")
                    c = info.get('codec')
                    if c:
                        codec_set.add(c)

            audio = hnm.extract_sound()
            audio_str = f"{len(audio) / 1024:.0f}K" if audio else "-"
            res_str = ', '.join(sorted(res)) if res else "-"
            codec_str = ', '.join(sorted(codec_set)) if codec_set else "-"

            print(f"{fname:<16} {len(data):>10,}  {hnm.frame_count:>6}  "
                  f"{audio_str:>8}  {res_str:<10}  {codec_str}")
        return 0

    for filepath in args.files:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}", file=sys.stderr)
            continue

        if args.extract or args.extract_sound or args.palette or args.frame_info is not None:
            data = open(filepath, 'rb').read()
            hnm = HnmFile(data)

            if args.palette:
                show_palette(hnm)
            elif args.frame_info is not None:
                info = hnm.get_frame_info(args.frame_info)
                if info:
                    print(f"Frame {args.frame_info}:")
                    for k, v in info.items():
                        if k == 'flags':
                            flags_str = []
                            if v & 0x02:
                                flags_str.append('compressed')
                            if v & 0x04:
                                flags_str.append('full-frame')
                            if v & 0x80:
                                flags_str.append('packbits')
                            print(f"  {k}: 0x{v:02X} ({', '.join(flags_str) if flags_str else 'none'})")
                        elif k == 'mode':
                            mode_str = 'opaque' if v == 0xFE else 'transparent' if v == 0xFF else f'0x{v:02X}'
                            print(f"  {k}: {mode_str}")
                        elif k == 'offset':
                            print(f"  {k}: 0x{v:08X}")
                        else:
                            print(f"  {k}: {v}")
                else:
                    print(f"Frame {args.frame_info} not found")
            elif args.extract_sound:
                audio = hnm.extract_sound()
                if audio:
                    write_wav(args.extract_sound, audio)
                    duration = len(audio) / 11111.0
                    print(f"Extracted {len(audio):,} bytes of audio ({duration:.1f}s) to {args.extract_sound}")
                else:
                    print("No audio data found in this HNM file")
            elif args.extract:
                print(f"Extracting frames from {os.path.basename(filepath)}...")
                extract_frames(hnm, args.extract, args.max_frames)
        else:
            analyze_hnm(filepath)
            print()

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
