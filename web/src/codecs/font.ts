/**
 * ReDune codecs — DNCHAR.BIN font decoder.
 * Port of the font logic in tools/bin_decoder.py.
 *
 * DNCHAR.BIN (2304 bytes, uncompressed):
 *   bytes 0..255   : per-character display width table
 *   bytes 256..    : 9 bytes per character = 9 rows of 8 pixels (MSB = leftmost)
 *   Height is always 9; 227 complete glyphs.
 */

export interface Glyph {
  width: number;
  rows: number[]; // 9 bytes, MSB = leftmost pixel
}

export const FONT_HEIGHT = 9;

export function decodeDnchar(data: Uint8Array): Glyph[] {
  const glyphs: Glyph[] = [];
  for (let i = 0; i < 256; i++) {
    const width = data[i] ?? 0;
    const base = 256 + i * FONT_HEIGHT;
    const rows = base + FONT_HEIGHT <= data.length ? Array.from(data.subarray(base, base + FONT_HEIGHT)) : new Array(FONT_HEIGHT).fill(0);
    glyphs.push({ width, rows });
  }
  return glyphs;
}

/** Pixel test: is (x,y) set in this glyph? x in 0..7 (MSB left), y in 0..8. */
export function glyphPixel(g: Glyph, x: number, y: number): boolean {
  if (y < 0 || y >= FONT_HEIGHT || x < 0 || x > 7) return false;
  return (g.rows[y] & (0x80 >> x)) !== 0;
}
