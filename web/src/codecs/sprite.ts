/**
 * ReDune codecs — sprite decoder.
 * Direct port of tools/sprite_decoder.py.
 *
 * Sprite HSQ file structure (decompressed):
 *   - uint16 LE @0: pointer to offset table (== palette end)
 *   - palette chunks at [2, pal_end)
 *   - offset table at pal_end: N × uint16 LE sprite offsets
 *   - sprite data: 4-byte header + 4-bit bipixel data (RLE or raw)
 */

import { hsqDecompress } from "./compression";

export type RGB = [number, number, number];

export interface Sprite {
  width: number;
  height: number;
  paletteOffset: number;
  compressed: boolean;
  /** palette indices, width*height (row-major) */
  pixels: Uint8Array;
}

export interface SpriteFile {
  data: Uint8Array; // decompressed
  palEnd: number;
  hasPalette: boolean;
  palette: Map<number, RGB>;
  count: number;
}

function u16(d: Uint8Array, o: number): number {
  return d[o] | (d[o + 1] << 8);
}

/** Decode VGA palette chunks; returns index -> [r,g,b] (0-255). */
export function decodePalette(data: Uint8Array, palEnd: number): Map<number, RGB> {
  const palette = new Map<number, RGB>();
  let pos = 2; // skip the uint16 offset
  while (pos + 1 < palEnd) {
    const startIdx = data[pos];
    const count = data[pos + 1];
    pos += 2;
    if (startIdx === 0xff && count === 0xff) break;
    for (let i = 0; i < count; i++) {
      if (pos + 2 >= data.length) break;
      const r = data[pos] & 0x3f;
      const g = data[pos + 1] & 0x3f;
      const b = data[pos + 2] & 0x3f;
      palette.set(startIdx + i, [
        Math.floor((r * 255) / 63),
        Math.floor((g * 255) / 63),
        Math.floor((b * 255) / 63),
      ]);
      pos += 3;
    }
  }
  return palette;
}

export function countSprites(data: Uint8Array): number {
  const palEnd = u16(data, 0);
  const firstSpriteOff = u16(data, palEnd);
  return firstSpriteOff >> 1;
}

/** Parse a sprite HSQ file (decompressing unless raw=true). */
export function loadSpriteFile(raw: Uint8Array, isRaw = false): SpriteFile {
  const data = isRaw ? raw : hsqDecompress(raw);
  if (data.length < 4) throw new Error("sprite file too small");
  const palEnd = u16(data, 0);
  const hasPalette = palEnd > 2;
  const palette = hasPalette ? decodePalette(data, palEnd) : new Map<number, RGB>();
  const count = countSprites(data);
  return { data, palEnd, hasPalette, palette, count };
}

/**
 * Heuristic: does this decompressed buffer look like a sprite sheet?
 * Used to warn when a non-CONDIT file is loaded into the CONDIT studio.
 * A real sprite file has a palette terminated by 0xFFFF, then an offset
 * table of sprites with plausible dimensions.
 */
export function looksLikeSprite(data: Uint8Array): boolean {
  try {
    if (data.length < 8) return false;
    const palEnd = u16(data, 0);
    if (palEnd < 2 || palEnd > data.length) return false;

    // Palette chunks (when present) must terminate with 0xFFFF inside [2, palEnd).
    if (palEnd > 2) {
      let pos = 2;
      let term = false;
      while (pos + 1 < palEnd) {
        if (data[pos] === 0xff && data[pos + 1] === 0xff) {
          term = true;
          break;
        }
        pos += 2 + data[pos + 1] * 3;
      }
      if (!term) return false;
    }

    const count = u16(data, palEnd) >> 1;
    if (count < 1 || count > 4096) return false;

    // First few sprite headers should have plausible dimensions.
    let good = 0;
    let checked = 0;
    for (let i = 0; i < Math.min(count, 6); i++) {
      const so = u16(data, palEnd + i * 2);
      const base = palEnd + so;
      if (base + 4 > data.length) continue;
      const w = data[base] + ((data[base + 1] & 0x7f) << 8);
      const h = data[base + 2];
      checked++;
      if (w >= 1 && w <= 640 && h >= 1 && h <= 400) good++;
    }
    return checked > 0 && good >= Math.ceil(checked * 0.8);
  } catch {
    return false;
  }
}

export function decodeSprite(data: Uint8Array, spriteIdx: number): Sprite {
  const palEnd = u16(data, 0);
  const offsetTableBase = palEnd;
  const hasExtra = palEnd === 2; // no palette -> 2 extra header bytes

  const spriteOff = u16(data, offsetTableBase + spriteIdx * 2);
  let pos = offsetTableBase + spriteOff;

  let width = data[pos];
  const compression = (data[pos + 1] & 0x80) !== 0;
  width += (data[pos + 1] & 0x7f) << 8;
  const height = data[pos + 2];
  const palOffset = data[pos + 3];
  pos += 4;
  if (hasExtra) pos += 2;

  if (width === 0 || height === 0) {
    return { width, height, paletteOffset: palOffset, compressed: compression, pixels: new Uint8Array(0) };
  }

  const pixels = new Uint8Array(width * height);
  let col = 0;
  let row = 0;
  let alignment = 0;

  const putBipixel = (bipixel: number) => {
    if (col < width) pixels[row * width + col] = palOffset + (bipixel & 0x0f);
    col++;
    alignment++;
    if (col < width) pixels[row * width + col] = palOffset + (bipixel >> 4);
    col++;
    alignment++;
  };

  if (compression) {
    while (row < height) {
      if (pos >= data.length) break;
      let rep = data[pos++];
      if (rep >= 128) rep -= 256; // signed

      if (rep < 0) {
        if (pos >= data.length) break;
        const bipixel = data[pos++];
        for (let k = 0; k < -rep + 1; k++) putBipixel(bipixel);
      } else {
        for (let k = 0; k < rep + 1; k++) {
          if (pos >= data.length) break;
          putBipixel(data[pos++]);
        }
      }
      if (col >= width) {
        col = 0;
        row++;
        const skip = (4 - (alignment % 4)) % 4;
        pos += skip;
        alignment = 0;
      }
    }
  } else {
    while (row < height) {
      if (pos + 1 >= data.length) break;
      const bp1 = data[pos];
      const bp2 = data[pos + 1];
      pos += 2;
      if (col < width) pixels[row * width + col] = palOffset + (bp1 & 0x0f);
      col++;
      if (col < width) pixels[row * width + col] = palOffset + (bp1 >> 4);
      col++;
      if (col < width) pixels[row * width + col] = palOffset + (bp2 & 0x0f);
      col++;
      if (col < width) pixels[row * width + col] = palOffset + (bp2 >> 4);
      col++;
      if (col >= width) {
        col = 0;
        row++;
      }
    }
  }

  return { width, height, paletteOffset: palOffset, compressed: compression, pixels };
}

/**
 * Render a decoded sprite to RGBA bytes for a canvas ImageData.
 * Palette index 0 is treated as transparent unless `opaque` is set.
 */
export function spriteToRGBA(sprite: Sprite, palette: Map<number, RGB>, opaque = false): Uint8ClampedArray {
  const { width, height, pixels } = sprite;
  const out = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < pixels.length; i++) {
    const idx = pixels[i];
    const rgb = palette.get(idx);
    const o = i * 4;
    if (rgb) {
      out[o] = rgb[0];
      out[o + 1] = rgb[1];
      out[o + 2] = rgb[2];
      out[o + 3] = !opaque && idx === 0 ? 0 : 255;
    } else {
      out[o] = out[o + 1] = out[o + 2] = 0;
      out[o + 3] = opaque ? 255 : 0;
    }
  }
  return out;
}
