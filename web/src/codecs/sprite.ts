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
  hasExtra: boolean;
  /** raw palette-chunk region [2, palEnd) incl. the 0xFFFF terminator (for re-encoding) */
  paletteBytes: Uint8Array;
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
  return {
    data,
    palEnd,
    hasPalette,
    hasExtra: palEnd === 2,
    paletteBytes: data.slice(2, palEnd),
    palette,
    count,
  };
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

export interface SpriteAnim {
  start: number; // first sprite index
  count: number; // number of frames
  width: number;
  height: number;
  paletteOffset: number;
}

/**
 * Recover candidate animation sequences from a sprite sheet: maximal runs of
 * consecutive sprites that share width×height×paletteOffset (≥ `minFrames`).
 *
 * This stays a structural heuristic by necessity. Disassembly of the VGA driver
 * overlays (DN386/DNVGA) confirmed they are *pure renderers*: the blit ABI
 * (entry @0x0E2D, clipped @0x1315) takes an explicit source pointer each call —
 * its nibble bipixel unpack, index-0 transparency and paletteOffset all match
 * this codec (validated line-by-line) — but the overlays hold **no frame-cel
 * sequence tables and no animation timer** (no int 1Ah / BDA-tick reads). The
 * cel order + timing live in the game-logic *caller* (the "CS1" main segment,
 * a binary we haven't disassembled), not in DNCDPRG.EXE nor these drivers. So
 * this heuristic (e.g. the 17-frame talking run in CHAN; PERS stays empty) is
 * the right meanwhile approach until that segment is recovered.
 */
export function detectAnimations(file: SpriteFile, minFrames = 2): SpriteAnim[] {
  const dims: { w: number; h: number; p: number }[] = [];
  for (let i = 0; i < file.count; i++) {
    try {
      const s = decodeSprite(file.data, i);
      dims.push({ w: s.width, h: s.height, p: s.paletteOffset });
    } catch {
      dims.push({ w: 0, h: 0, p: 0 });
    }
  }
  const out: SpriteAnim[] = [];
  let st = 0;
  for (let i = 1; i <= dims.length; i++) {
    const same = i < dims.length && dims[i].w === dims[st].w && dims[i].h === dims[st].h && dims[i].p === dims[st].p;
    if (!same) {
      const count = i - st;
      if (count >= minFrames && dims[st].w > 0 && dims[st].h > 0) {
        out.push({ start: st, count, width: dims[st].w, height: dims[st].h, paletteOffset: dims[st].p });
      }
      st = i;
    }
  }
  return out;
}

export interface EncSprite {
  width: number;
  height: number;
  paletteOffset: number;
  pixels: Uint8Array; // palette indices, width*height
  /** Verbatim original body bytes; when set, emitted as-is (byte-identical
   * passthrough for unedited sprites — `pixels` etc. are then ignored). */
  raw?: Uint8Array;
}

/**
 * Verbatim body bytes (4-byte header + bipixel data) of sprite `i`, sliced from
 * the original file. Used to round-trip unedited sprites byte-identically: the
 * RLE-compressed stream is non-unique, so re-compressing wouldn't match — but
 * passing the original bytes through does.
 */
export function spriteBody(file: SpriteFile, i: number): Uint8Array {
  const base = file.palEnd;
  const start = base + u16(file.data, base + i * 2);
  // End = the next body that starts after `start` (offsets need not be in index
  // order), or end-of-file for the last one.
  let end = file.data.length;
  for (let j = 0; j < file.count; j++) {
    const o = base + u16(file.data, base + j * 2);
    if (o > start && o < end) end = o;
  }
  return file.data.subarray(start, end);
}

/**
 * Encode a sprite file (raw / uncompressed mode). The output decodes back to
 * the exact same sprites & palette (decode-equivalent round-trip), so it is a
 * valid replacement file the game/decoder reads. `paletteBytes` is the raw
 * [2,palEnd) region (reuse loadSpriteFile().paletteBytes to preserve the palette).
 */
export function encodeSpriteFile(opts: { paletteBytes: Uint8Array; hasExtra: boolean; sprites: EncSprite[] }): Uint8Array {
  const { paletteBytes, hasExtra, sprites } = opts;
  const palEnd = 2 + paletteBytes.length;

  const bodies: number[][] = sprites.map((s) => {
    if (s.raw) return Array.from(s.raw); // verbatim passthrough (unedited sprite)
    const body: number[] = [s.width & 0xff, (s.width >> 8) & 0x7f, s.height & 0xff, s.paletteOffset & 0xff];
    if (hasExtra) body.push(0, 0);
    const nib = (px: number) => (px - s.paletteOffset) & 0x0f;
    for (let row = 0; row < s.height; row++) {
      for (let col = 0; col < s.width; col += 4) {
        const at = (c: number) => (c < s.width ? s.pixels[row * s.width + c] : s.paletteOffset);
        const p0 = nib(at(col));
        const p1 = nib(at(col + 1));
        const p2 = nib(at(col + 2));
        const p3 = nib(at(col + 3));
        body.push(p0 | (p1 << 4), p2 | (p3 << 4));
      }
    }
    return body;
  });

  const n = sprites.length;
  const tableSize = n * 2;
  const offsets: number[] = [];
  let pos = tableSize;
  for (const b of bodies) {
    offsets.push(pos);
    pos += b.length;
  }

  const out: number[] = [palEnd & 0xff, (palEnd >> 8) & 0xff];
  for (const x of paletteBytes) out.push(x);
  for (const off of offsets) out.push(off & 0xff, (off >> 8) & 0xff);
  for (const b of bodies) for (const x of b) out.push(x);
  return Uint8Array.from(out);
}

/**
 * Map an RGBA image to a sprite's 16-colour window [palOffset, palOffset+15]
 * by nearest-colour matching. Returns palette indices (width*height).
 */
export function quantizeToSprite(rgba: Uint8ClampedArray | Uint8Array, width: number, height: number, palette: Map<number, RGB>, palOffset: number): Uint8Array {
  const cand: { idx: number; rgb: RGB }[] = [];
  for (let i = 0; i < 16; i++) {
    const rgb = palette.get(palOffset + i);
    if (rgb) cand.push({ idx: palOffset + i, rgb });
  }
  const out = new Uint8Array(width * height);
  if (cand.length === 0) return out;
  for (let p = 0; p < width * height; p++) {
    const o = p * 4;
    const r = rgba[o];
    const g = rgba[o + 1];
    const b = rgba[o + 2];
    const a = rgba[o + 3];
    if (a < 128) {
      out[p] = palOffset; // transparent -> base index (index 0 convention)
      continue;
    }
    let best = cand[0];
    let bd = Infinity;
    for (const c of cand) {
      const dr = r - c.rgb[0];
      const dg = g - c.rgb[1];
      const db = b - c.rgb[2];
      const d = dr * dr + dg * dg + db * db;
      if (d < bd) {
        bd = d;
        best = c;
      }
    }
    out[p] = best.idx;
  }
  return out;
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
