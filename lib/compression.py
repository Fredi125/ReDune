"""
dune1992-re: Core compression/decompression library.

Implements:
  - HSQ (LZ77-variant) decompression used for game resources
  - F7 RLE compression/decompression used for save files
"""

import struct


# =============================================================================
# HSQ DECOMPRESSION (Game resource files: *.HSQ)
# =============================================================================

def hsq_decompress(data: bytes) -> bytes:
    """
    Decompress HSQ (Cryo Interactive LZ77-variant) compressed data.

    HSQ header (6 bytes):
      - uint16 LE: decompressed size
      - uint8:     skip byte
      - uint16 LE: compressed size (should == file size)
      - uint8:     skip byte

    Bitstream LZ77 decoder using 16-bit queue with sentinel:
      - Bit 1: literal byte
      - Bit 0, bit 1: long back-reference (word: 3-bit count, 13-bit offset)
        - count==0: read extra byte for count; count==0 again = EOF
      - Bit 0, bit 0: short back-reference (2 bits count, byte offset -256)

    Reference: OpenRakis/tools/cd/UnHsq/Program.cs

    Args:
        data: Raw HSQ file contents

    Returns:
        Decompressed bytes

    Raises:
        ValueError: If data is invalid
    """
    if len(data) < 6:
        raise ValueError(f"HSQ data too short: {len(data)} bytes")

    decomp_size = struct.unpack_from('<H', data, 0)[0]
    # byte 2 is skipped
    comp_size = struct.unpack_from('<H', data, 3)[0]
    # byte 5 is skipped

    pos = 6
    queue = 0  # 16-bit bit queue; 0 means "needs refill"
    out = bytearray()

    def read_u8():
        nonlocal pos
        if pos >= len(data):
            raise ValueError(f"HSQ: unexpected end at offset {pos}")
        val = data[pos]; pos += 1
        return val

    def read_u16():
        nonlocal pos
        if pos + 1 >= len(data):
            raise ValueError(f"HSQ: unexpected end at offset {pos}")
        val = struct.unpack_from('<H', data, pos)[0]; pos += 2
        return val

    def get_bit():
        nonlocal queue
        bit = queue & 1
        queue >>= 1
        if queue == 0:
            queue = read_u16()
            bit = queue & 1
            queue = 0x8000 | (queue >> 1)
        return bit

    while True:
        if get_bit() != 0:
            # Literal byte
            if len(out) >= decomp_size:
                break
            out.append(read_u8())
        else:
            if get_bit() != 0:
                # Long back-reference
                word = read_u16()
                count = word & 0x07
                offset = (word >> 3) - 8192  # signed negative offset

                if count == 0:
                    count = read_u8()
                if count == 0:
                    break  # EOF

                # Copy count+2 bytes from (dst + offset)
                dst = len(out)
                for i in range(count + 2):
                    out.append(out[dst + offset + i])
            else:
                # Short back-reference
                b0 = get_bit()
                b1 = get_bit()
                count = 2 * b0 + b1  # 0-3
                offset = read_u8() - 256  # signed negative offset

                dst = len(out)
                for i in range(count + 2):
                    out.append(out[dst + offset + i])

    return bytes(out[:decomp_size])


def hsq_get_sizes(data: bytes) -> tuple:
    """
    Read HSQ header without decompressing.

    Header layout (6 bytes):
      uint16 LE: decompressed size
      uint8:     checksum byte
      uint16 LE: compressed size (== file size)
      uint8:     checksum byte (copy)

    Returns:
        (decompressed_size, compressed_size, checksum)
    """
    if len(data) < 6:
        raise ValueError("Not an HSQ file (too short)")
    decomp = struct.unpack_from('<H', data, 0)[0]
    checksum = data[2]
    comp = struct.unpack_from('<H', data, 3)[0]
    return (decomp, comp, checksum)


# =============================================================================
# F7 RLE COMPRESSION (Save files: DUNE*.SAV)
# =============================================================================

def f7_decompress(data: bytes) -> bytearray:
    """
    Decompress F7 RLE encoded save file data.

    F7 RLE format (from DuneEdit2 SequenceParser.cs):
      - F7 01 F7: control sequence → literal 0xF7 byte
      - F7 NN VV (NN > 2): repeat byte VV exactly NN times
      - Any other byte: literal

    Args:
        data: Raw save file contents

    Returns:
        Decompressed bytearray
    """
    out = bytearray()
    i = 0
    end = len(data) - 3  # leave room for 3-byte lookahead

    while i <= end:
        b0, b1, b2 = data[i], data[i + 1], data[i + 2]

        if b0 == 0xF7 and b1 == 0x01 and b2 == 0xF7:
            # Control sequence: literal 0xF7
            out.append(0xF7)
            i += 3
        elif b0 == 0xF7 and b1 > 2:
            # RLE: repeat b2 exactly b1 times
            out.extend(bytes([b2]) * b1)
            i += 3
        else:
            out.append(b0)
            if i == end:
                # Last 3 bytes: output remaining
                out.append(b1)
                out.append(b2)
            i += 1

    # Handle any remaining bytes after the loop
    while i < len(data):
        out.append(data[i])
        i += 1

    return out


def f7_compress(data: bytes) -> bytearray:
    """
    Compress data with F7 RLE encoding (inverse of f7_decompress).

    Encoding rules:
      - Literal 0xF7 → F7 01 F7 (control sequence)
      - Run of N > 3 identical bytes → F7 NN VV
      - All other bytes → literal

    Args:
        data: Uncompressed save file data

    Returns:
        Compressed bytearray
    """
    out = bytearray()
    i = 0

    while i < len(data):
        b = data[i]

        if b == 0xF7:
            # Literal F7 → control sequence
            out.extend(b'\xF7\x01\xF7')
            i += 1
            continue

        # Count run of identical bytes (max 255)
        run = 1
        while i + run < len(data) and data[i + run] == b and run < 255:
            run += 1

        if run > 3:
            # RLE encode
            out.extend(bytes([0xF7, run, b]))
            i += run
        else:
            out.append(b)
            i += 1

    return out
