/**
 * ReDune codecs — LOP background-animation decoder + recompiler.
 * Port of tools/lop_decoder.py.
 *
 * A LOP file is a 24-byte header (size, 0xFFFF marker, 4 section offsets, pad)
 * followed by up to 4 sections. Each section has an 11-byte header
 * (stored_size, x, y, width, mode, flags, height, reserved, data_size) then
 * PackBits-compressed 8-bit indexed pixels.
 */
import { isHsq, hsqDecompress } from "./compression";

export const SECTION_COUNT = 4;
export const FILE_HEADER_SIZE = 24;

export interface LopSection {
  index: number;
  x: number;
  y: number;
  width: number;
  height: number;
  mode: number;
  flags: number;
  compressed: boolean;
  pixelData: Uint8Array;
  raw: Uint8Array; // verbatim section bytes (for byte-identical reassembly)
}

export interface LopFile {
  headerSize: number;
  marker: number;
  sectionOffsets: number[];
  sections: LopSection[];
  data: Uint8Array; // decompressed source (encoder input)
}

const u16 = (d: Uint8Array, o: number) => d[o] | (d[o + 1] << 8);
const u32 = (d: Uint8Array, o: number) => (d[o] | (d[o + 1] << 8) | (d[o + 2] << 16) | (d[o + 3] << 24)) >>> 0;

export function parseLop(raw: Uint8Array): LopFile {
  const data = isHsq(raw) ? hsqDecompress(raw) : raw;
  if (data.length < FILE_HEADER_SIZE) throw new Error(`LOP too small (${data.length} bytes)`);
  const headerSize = u16(data, 0);
  const marker = u16(data, 2);
  const sectionOffsets: number[] = [];
  for (let i = 0; i < SECTION_COUNT; i++) sectionOffsets.push(u32(data, 4 + i * 4));

  const sections: LopSection[] = [];
  for (let i = 0; i < SECTION_COUNT; i++) {
    const start = FILE_HEADER_SIZE + sectionOffsets[i];
    const end = i + 1 < SECTION_COUNT ? FILE_HEADER_SIZE + sectionOffsets[i + 1] : data.length;
    if (start >= data.length || end > data.length || end - start < 11) continue;
    const s = data.subarray(start, end);
    sections.push({
      index: i,
      x: s[2],
      y: s[3],
      width: s[4],
      mode: s[5],
      flags: s[6],
      height: s[7],
      compressed: (s[6] & 0x80) !== 0,
      pixelData: s.subarray(11),
      raw: s,
    });
  }
  return { headerSize, marker, sectionOffsets, sections, data };
}

/** Decode PackBits pixels. RLE: cmd&0x80 → repeat next byte (257-cmd) times. */
export function decodePackbits(pixelData: Uint8Array, width: number, height: number): Uint8Array {
  const target = width * height;
  const out = new Uint8Array(target);
  let pos = 0;
  let o = 0;
  while (pos < pixelData.length && o < target) {
    const cmd = pixelData[pos++];
    if (cmd & 0x80) {
      const count = 257 - cmd;
      if (pos >= pixelData.length) break;
      const val = pixelData[pos++];
      for (let k = 0; k < count && o < target; k++) out[o++] = val;
    } else {
      const count = cmd + 1;
      for (let k = 0; k < count; k++) {
        if (pos >= pixelData.length || o >= target) break;
        out[o++] = pixelData[pos++];
      }
    }
  }
  return out;
}

/** Compress raw pixels to LOP PackBits (decodePackbits(encodePackbits(px))===px). */
export function encodePackbits(pixels: Uint8Array): Uint8Array {
  const out: number[] = [];
  let i = 0;
  const n = pixels.length;
  while (i < n) {
    let run = 1;
    while (i + run < n && pixels[i + run] === pixels[i] && run < 129) run++;
    if (run >= 2) {
      out.push(257 - run, pixels[i]);
      i += run;
    } else {
      const start = i;
      let lit = 0;
      while (i < n && lit < 128) {
        if (i + 1 < n && pixels[i + 1] === pixels[i]) break;
        i++;
        lit++;
      }
      out.push(lit - 1);
      for (let k = start; k < start + lit; k++) out.push(pixels[k]);
    }
  }
  return Uint8Array.from(out);
}

/**
 * Reassemble a LOP file from raw section byte-strings (inverse of parseLop).
 * Byte-identical when `sections` are the verbatim `LopSection.raw` slices; the
 * 24-byte header (marker + padding) is preserved, only the offset table @4 is
 * repatched.
 */
export function encodeLop(file: LopFile, sections?: Uint8Array[]): Uint8Array {
  const secs = sections ?? file.sections.map((s) => s.raw);
  const header = file.data.slice(0, FILE_HEADER_SIZE);
  let cur = 0;
  for (let i = 0; i < SECTION_COUNT; i++) {
    header[4 + i * 4] = cur & 0xff;
    header[4 + i * 4 + 1] = (cur >> 8) & 0xff;
    header[4 + i * 4 + 2] = (cur >> 16) & 0xff;
    header[4 + i * 4 + 3] = (cur >> 24) & 0xff;
    if (i < secs.length) cur += secs[i].length;
  }
  const total = FILE_HEADER_SIZE + secs.reduce((a, s) => a + s.length, 0);
  const out = new Uint8Array(total);
  out.set(header, 0);
  let p = FILE_HEADER_SIZE;
  for (const s of secs) {
    out.set(s, p);
    p += s.length;
  }
  return out;
}
