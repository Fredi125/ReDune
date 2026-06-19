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

/** Set/clear a glyph pixel in place. */
export function setGlyphPixel(g: Glyph, x: number, y: number, on: boolean): void {
  if (y < 0 || y >= FONT_HEIGHT || x < 0 || x > 7) return;
  if (on) g.rows[y] |= 0x80 >> x;
  else g.rows[y] &= ~(0x80 >> x) & 0xff;
}

/**
 * Encode glyphs back to a DNCHAR.BIN. Pass the `original` buffer to preserve its
 * exact length and any trailing partial-glyph bytes the decoder doesn't model —
 * only the width table and *complete* glyphs are overwritten, so an unedited
 * round-trip is byte-identical. Without `original`, writes a full 256-glyph file.
 */
export function encodeDnchar(glyphs: Glyph[], original?: Uint8Array): Uint8Array {
  const out = original ? original.slice() : new Uint8Array(256 + 256 * FONT_HEIGHT);
  for (let i = 0; i < 256; i++) {
    const g = glyphs[i];
    if (!g) continue;
    if (i < out.length) out[i] = g.width & 0xff;
    const base = 256 + i * FONT_HEIGHT;
    if (base + FONT_HEIGHT <= out.length) {
      for (let y = 0; y < FONT_HEIGHT; y++) out[base + y] = (g.rows[y] ?? 0) & 0xff;
    }
  }
  return out;
}
