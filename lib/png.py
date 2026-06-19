"""
dune1992-re: Pure-Python PNG writer (stdlib only).

Implements a minimal but spec-compliant PNG encoder using only the standard
library (``zlib`` for IDAT compression, ``struct`` for chunk framing, and
``zlib.crc32`` for chunk CRCs). No third-party dependencies.

Supports two color types:
  - 24-bit truecolor (PNG color type 2): ``encode_png``
  - 32-bit truecolor + alpha (PNG color type 6): ``encode_png_rgba``

Reference: PNG spec (RFC 2083). Each chunk is:
  uint32 BE length | 4-byte type | data | uint32 BE CRC32(type + data)
Scanlines are prefixed with a filter byte (0 = None) before deflate.
"""

import struct
import zlib

# 8-byte PNG file signature.
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Build one PNG chunk: length, type, data, CRC32(type+data)."""
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack('>I', len(data)) + chunk_type + data + struct.pack('>I', crc)


def _encode(width: int, height: int, pixels: bytes, color_type: int,
            channels: int) -> bytes:
    """Encode raw pixel bytes into a PNG of the given color type.

    Args:
        width:      Image width in pixels.
        height:     Image height in pixels.
        pixels:     Raw pixel data, ``width * height * channels`` bytes,
                    row-major, top-to-bottom.
        color_type: PNG color type (2 = RGB, 6 = RGBA).
        channels:   Bytes per pixel (3 for RGB, 4 for RGBA).

    Returns:
        Complete PNG file as bytes.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid dimensions: {width}x{height}")
    expected = width * height * channels
    if len(pixels) != expected:
        raise ValueError(
            f"pixel buffer is {len(pixels)} bytes, expected {expected} "
            f"({width}x{height}x{channels})")

    # Build the raw scanline stream: each row prefixed with filter byte 0.
    stride = width * channels
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        row_start = y * stride
        raw += pixels[row_start:row_start + stride]

    # IHDR: width, height, bit depth, color type, compression, filter, interlace
    ihdr = struct.pack('>IIBBBBB', width, height, 8, color_type, 0, 0, 0)

    idat = zlib.compress(bytes(raw), 9)

    return (PNG_SIGNATURE
            + _chunk(b'IHDR', ihdr)
            + _chunk(b'IDAT', idat)
            + _chunk(b'IEND', b''))


def encode_png(width: int, height: int, rgb: bytes) -> bytes:
    """Encode 24-bit RGB pixel data into a PNG.

    Args:
        width:  Image width in pixels.
        height: Image height in pixels.
        rgb:    ``width * height * 3`` bytes (R, G, B per pixel, row-major).

    Returns:
        Complete PNG file as bytes.
    """
    return _encode(width, height, rgb, color_type=2, channels=3)


def encode_png_rgba(width: int, height: int, rgba: bytes) -> bytes:
    """Encode 32-bit RGBA pixel data into a PNG.

    Args:
        width:  Image width in pixels.
        height: Image height in pixels.
        rgba:   ``width * height * 4`` bytes (R, G, B, A per pixel, row-major).

    Returns:
        Complete PNG file as bytes.
    """
    return _encode(width, height, rgba, color_type=6, channels=4)


def write_png(path: str, width: int, height: int, rgb: bytes) -> None:
    """Encode 24-bit RGB data and write it to ``path``."""
    with open(path, 'wb') as f:
        f.write(encode_png(width, height, rgb))


def write_png_rgba(path: str, width: int, height: int, rgba: bytes) -> None:
    """Encode 32-bit RGBA data and write it to ``path``."""
    with open(path, 'wb') as f:
        f.write(encode_png_rgba(width, height, rgba))
