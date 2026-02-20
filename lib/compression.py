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
# HSQ COMPRESSION (Game resource files: *.HSQ)
# =============================================================================

def hsq_compress(data: bytes) -> bytes:
    """
    Compress data with HSQ (Cryo Interactive LZ77-variant) encoding.

    Produces output compatible with hsq_decompress(). Uses greedy matching
    with the same three command types as the original format:
      - Literal byte (1 bit overhead + byte)
      - Short back-reference: offset -256..-1, length 2-5 (4 bits + byte)
      - Long back-reference: offset -8192..-1, length 3-257 (2 bits + word [+byte])

    HSQ header checksum: sum of all 6 header bytes ≡ 0xAB (mod 256).

    Args:
        data: Uncompressed data

    Returns:
        HSQ-compressed bytes with valid header
    """
    src_len = len(data)
    if src_len == 0:
        # Empty data: just header + EOF
        # EOF = bits 0,1 (long ref prefix) + word 0x0000 (count=0) + byte 0x00
        # Bit word: bit0=0, bit1=1, rest zero (16 raw data bits, no sentinel)
        eof_bits = (0 << 0) | (1 << 1)  # 0x0002
        body = struct.pack('<H', eof_bits) + struct.pack('<H', 0) + bytes([0])
        hdr = bytearray(6)
        struct.pack_into('<H', hdr, 0, 0)
        hdr[2] = 0x00
        struct.pack_into('<H', hdr, 3, 6 + len(body))
        hdr[5] = (0xAB - hdr[0] - hdr[1] - hdr[2] - hdr[3] - hdr[4]) & 0xFF
        return bytes(hdr) + body

    # --- LZ77 hash-chain matching ---
    # Hash table maps 3-byte sequences to most recent position;
    # chain array links positions with matching hashes for fast lookup.
    HASH_SIZE = 1 << 15  # 32K hash table
    HASH_MASK = HASH_SIZE - 1
    MAX_CHAIN = 64  # max chain depth to search

    head = [-1] * HASH_SIZE  # hash → most recent position
    prev = [0] * src_len     # position → previous position with same hash

    def hash3(p):
        if p + 2 >= src_len:
            return 0
        return ((data[p] << 10) ^ (data[p + 1] << 5) ^ data[p + 2]) & HASH_MASK

    commands = []
    pos = 0

    while pos < src_len:
        best_len = 0
        best_off = 0
        max_len = min(src_len - pos, 257)

        if pos + 2 < src_len:
            h = hash3(pos)
            match_pos = head[h]
            chain_count = 0
            min_pos = max(0, pos - 8192)

            while match_pos >= min_pos and chain_count < MAX_CHAIN:
                # Check match length
                ml = 0
                while ml < max_len and data[pos + ml] == data[match_pos + ml]:
                    ml += 1
                if ml > best_len:
                    best_len = ml
                    best_off = pos - match_pos
                    if best_len >= max_len:
                        break
                chain_count += 1
                next_pos = prev[match_pos]
                if next_pos >= match_pos:
                    break  # avoid infinite loop
                match_pos = next_pos

            # Insert current position into hash chain
            prev[pos] = head[h] if head[h] >= 0 else pos
            head[h] = pos
        else:
            # Near end of data, update hash for completeness
            if pos + 2 < src_len:
                h = hash3(pos)
                prev[pos] = head[h] if head[h] >= 0 else pos
                head[h] = pos

        if best_off <= 256 and best_len >= 2:
            # Short back-reference (offset -256..-1, length 2-5)
            use_len = min(best_len, 5)
            count_bits = use_len - 2
            offset_byte = (-best_off) & 0xFF
            commands.append(('short', count_bits, offset_byte))
            # Insert skipped positions into hash chain
            for j in range(1, use_len):
                if pos + j + 2 < src_len:
                    hj = hash3(pos + j)
                    prev[pos + j] = head[hj] if head[hj] >= 0 else pos + j
                    head[hj] = pos + j
            pos += use_len
        elif best_len >= 3:
            # Long back-reference
            offset_13 = ((-best_off) + 8192) & 0x1FFF
            copy_count = best_len - 2

            if 1 <= copy_count <= 7:
                word = (offset_13 << 3) | copy_count
                commands.append(('long', word))
            else:
                word = (offset_13 << 3) | 0
                commands.append(('long_ext', word, copy_count & 0xFF))

            # Insert skipped positions into hash chain
            for j in range(1, best_len):
                if pos + j + 2 < src_len:
                    hj = hash3(pos + j)
                    prev[pos + j] = head[hj] if head[hj] >= 0 else pos + j
                    head[hj] = pos + j
            pos += best_len
        else:
            commands.append(('literal', data[pos]))
            pos += 1

    # EOF marker: long ref with count=0, extra_byte=0
    commands.append(('long_ext', 0, 0))

    # --- Encode bit stream ---
    # The decompressor reads bits from uint16 words with a sentinel.
    # Each uint16 provides 16 data bits: bit 0 from refill, bits 1-15 from queue.
    # The sentinel at queue[15] is added by the decompressor (0x8000 | word>>1),
    # so the compressor writes all 16 bits as raw data.
    class BitWriter:
        def __init__(self):
            self.stream = bytearray()
            self.word_bits = []  # current word's bits (up to 16)
            self.word_pos = -1   # position in stream where current word will go

        def _start_word(self):
            """Reserve space for a uint16 bit word."""
            self.word_pos = len(self.stream)
            self.stream.extend(b'\x00\x00')  # placeholder
            self.word_bits = []

        def write_bit(self, b):
            if self.word_pos < 0 or len(self.word_bits) >= 16:
                self._flush_word()
                self._start_word()
            self.word_bits.append(b & 1)

        def write_byte(self, b):
            self.stream.append(b & 0xFF)

        def write_word(self, w):
            self.stream.extend(struct.pack('<H', w & 0xFFFF))

        def _flush_word(self):
            if self.word_pos < 0:
                return
            # Pad to 16 bits — the decompressor adds its own sentinel
            # via 0x8000 | (word >> 1), so all 16 bits are data
            while len(self.word_bits) < 16:
                self.word_bits.append(0)
            word = 0
            for i, b in enumerate(self.word_bits[:16]):
                word |= ((b & 1) << i)
            struct.pack_into('<H', self.stream, self.word_pos, word)
            self.word_bits = []
            self.word_pos = -1

        def finish(self):
            if self.word_pos >= 0:
                self._flush_word()
            return bytes(self.stream)

    w = BitWriter()

    for cmd in commands:
        if cmd[0] == 'literal':
            w.write_bit(1)
            w.write_byte(cmd[1])
        elif cmd[0] == 'short':
            count_bits, offset_byte = cmd[1], cmd[2]
            w.write_bit(0)
            w.write_bit(0)
            w.write_bit((count_bits >> 1) & 1)  # b0 in decompressor
            w.write_bit(count_bits & 1)          # b1 in decompressor
            w.write_byte(offset_byte)
        elif cmd[0] == 'long':
            word = cmd[1]
            w.write_bit(0)
            w.write_bit(1)
            w.write_word(word)
        elif cmd[0] == 'long_ext':
            word, extra = cmd[1], cmd[2]
            w.write_bit(0)
            w.write_bit(1)
            w.write_word(word)
            w.write_byte(extra)

    compressed_body = w.finish()

    # --- Build header ---
    decomp_size = src_len
    comp_size = 6 + len(compressed_body)

    hdr = bytearray(6)
    struct.pack_into('<H', hdr, 0, decomp_size & 0xFFFF)
    hdr[2] = 0x00
    struct.pack_into('<H', hdr, 3, comp_size & 0xFFFF)
    hdr[5] = (0xAB - hdr[0] - hdr[1] - hdr[2] - hdr[3] - hdr[4]) & 0xFF

    return bytes(hdr) + compressed_body


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
