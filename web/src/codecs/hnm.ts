/**
 * ReDune codecs — HNM video decoder.
 * Port of tools/hnm_decoder.py. Chunk-based format: a header chunk (palette +
 * frame offset table) followed by AV frame chunks with tagged sub-chunks:
 *   'pl' (0x6C70) palette update, 'sd' (0x6473) sound, 'mm' (0x6D6D) metadata,
 *   else a 4-byte video frame header + frame data (LZ/HSQ, AD, or raw).
 *
 * All shipped game videos use LZ (HSQ) frames (validated vs Python via per-frame
 * framebuffer checksums); the AD codec is ported for completeness.
 */
import { hsqDecompress } from "./compression";

function u16(d: Uint8Array, o: number): number {
  return d[o] | (d[o + 1] << 8);
}
function u32(d: Uint8Array, o: number): number {
  return (d[o] | (d[o + 1] << 8) | (d[o + 2] << 16) | (d[o + 3] << 24)) >>> 0;
}

export function parsePaletteBlock(data: Uint8Array, pos: number): { palette: Uint8Array; pos: number } {
  const palette = new Uint8Array(768);
  while (pos + 1 < data.length) {
    const word = u16(data, pos);
    pos += 2;
    if (word === 0xffff) break;
    if (word === 0x0100) {
      pos += 3;
      continue;
    }
    const startIdx = word & 0xff;
    let count = (word >> 8) & 0xff;
    if (count === 0) count = 256;
    for (let i = 0; i < count; i++) {
      if (pos + 2 >= data.length) break;
      const idx = (startIdx + i) * 3;
      if (idx + 2 < palette.length) {
        const r = data[pos];
        const g = data[pos + 1];
        const b = data[pos + 2];
        palette[idx] = (r << 2) | (r >> 4);
        palette[idx + 1] = (g << 2) | (g >> 4);
        palette[idx + 2] = (b << 2) | (b >> 4);
      }
      pos += 3;
    }
  }
  return { palette, pos };
}

export function frameChecksum(data: Uint8Array, off = 0): number {
  if (data.length - off < 6) return 0;
  let s = 0;
  for (let i = 0; i < 6; i++) s += data[off + i];
  return s & 0xff;
}

export function renderFrame(
  pixel: Uint8Array,
  framebuf: Uint8Array,
  xOff: number,
  yOff: number,
  w: number,
  h: number,
  flags: number,
  mode: number,
  srcOffset = 0,
): void {
  if (w === 0 || h === 0) return;
  if (flags & 0x80) {
    let pos = srcOffset;
    for (let y = 0; y < h; y++) {
      const dstBase = 320 * (y + yOff) + xOff;
      let lineRemain = w;
      while (lineRemain > 0 && pos < pixel.length) {
        const cmd = pixel[pos++];
        if (cmd & 0x80) {
          const count = 257 - cmd;
          if (pos >= pixel.length) break;
          const value = pixel[pos++];
          for (let i = 0; i < count; i++) {
            if (lineRemain <= 0) break;
            const dst = dstBase + (w - lineRemain);
            if (!(mode === 0xff && value === 0) && dst >= 0 && dst < 64000) framebuf[dst] = value;
            lineRemain--;
          }
        } else {
          const count = cmd + 1;
          for (let i = 0; i < count; i++) {
            if (lineRemain <= 0 || pos >= pixel.length) break;
            const value = pixel[pos++];
            const dst = dstBase + (w - lineRemain);
            if (!(mode === 0xff && value === 0) && dst >= 0 && dst < 64000) framebuf[dst] = value;
            lineRemain--;
          }
        }
      }
    }
  } else {
    let pos = srcOffset;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        if (pos >= pixel.length) return;
        const value = pixel[pos++];
        const dst = 320 * (y + yOff) + (x + xOff);
        if (mode === 0xff && value === 0) continue;
        if (dst >= 0 && dst < 64000) framebuf[dst] = value;
      }
    }
  }
}

/** AD-codec frame decode (codebook + RLE). Ported for completeness; unused by shipped videos. */
export function decompressFrameAd(data: Uint8Array): { output: Uint8Array; x: number; y: number } {
  if (data.length < 6) return { output: new Uint8Array(0), x: 0, y: 0 };
  const framesize = u16(data, 0);
  const codebooksize = u16(data, 2);
  const flags = data[4];
  let pos = 6;
  let x = 0;
  let y = 0;
  if (!(flags & 0x04)) {
    x = u16(data, pos);
    y = u16(data, pos + 2);
    pos += 4;
  }
  const colorbase = flags & 0x40 ? 0x80 : 0;
  const codebook = new Uint8Array(codebooksize);
  let cbPos = 0;
  let flip = 0;
  let oVal = 0;
  let inp = pos;
  while (cbPos < codebooksize && inp < data.length) {
    let tag = data[inp++];
    if (tag & 0x80) {
      let length: number;
      if (!flip) {
        if (inp >= data.length) break;
        oVal = data[inp++];
        length = oVal >> 4;
      } else length = oVal & 0x0f;
      flip ^= 1;
      const ofsVal = (tag << 1) | (length & 1);
      length = (length >> 1) + 2;
      for (let k = 0; k < length; k++) {
        if (cbPos >= codebooksize) break;
        const src = cbPos - ofsVal - 1;
        if (src >= 0 && src < cbPos) codebook[cbPos] = codebook[src];
        cbPos++;
      }
    } else {
      if (tag) tag = (tag + colorbase) & 0xff;
      if (cbPos < codebooksize) codebook[cbPos] = tag;
      cbPos++;
    }
  }
  const output = new Uint8Array(framesize);
  let outPos = 0;
  let tempPos = 0;
  let flip2 = 0;
  let oVal2 = 0;
  let queue = 0x8000;
  const getBit = (): number => {
    if (queue === 0x8000) {
      if (inp + 1 >= data.length) return 0;
      const word = u16(data, inp);
      inp += 2;
      queue = ((word << 1) | 1) >>> 0;
      return (word >> 15) & 1;
    }
    const result = (queue >>> 15) & 1;
    if (queue & 0x8000) queue = ((queue << 1) | 0x8000) >>> 0;
    else queue = (queue << 1) & 0x7fff;
    return result;
  };
  const emit = (c: number, n: number) => {
    for (let k = 0; k < n; k++) if (outPos < framesize) output[outPos++] = c;
  };
  const longRun = (): number => {
    let runLen: number;
    if (!flip2) {
      if (inp >= data.length) return -1;
      oVal2 = data[inp++];
      runLen = oVal2 >> 4;
    } else runLen = oVal2 & 0x0f;
    flip2 ^= 1;
    if (runLen === 0) {
      if (inp >= data.length) return -1;
      runLen = data[inp++] + 16;
    }
    return runLen + 4;
  };
  const alt = (flags & 0x80) !== 0;
  while (outPos < framesize && tempPos < codebooksize) {
    while (!getBit()) {
      if (tempPos >= codebooksize || outPos >= framesize) break;
      output[outPos++] = codebook[tempPos++];
    }
    if (tempPos >= codebooksize || outPos >= framesize) break;
    const c = codebook[tempPos++];
    if (!alt) {
      if (!getBit()) emit(c, 2);
      else if (!getBit()) emit(c, 3);
      else if (!getBit()) emit(c, 4);
      else {
        if (outPos >= framesize) break;
        const n = longRun();
        if (n < 0) break;
        emit(c, n);
      }
    } else {
      if (!getBit()) {
        const n = longRun();
        if (n < 0) break;
        emit(c, n);
      } else if (!getBit()) emit(c, 2);
      else if (!getBit()) emit(c, 3);
      else {
        if (outPos >= framesize) break;
        emit(c, 4);
      }
    }
  }
  return { output, x, y };
}

export class HnmFile {
  data: Uint8Array;
  palette: Uint8Array = new Uint8Array(768);
  headerSize = 0;
  frameOffsets: number[] = [];
  frameCount = 0;

  constructor(data: Uint8Array) {
    this.data = data;
    this.parse();
  }

  private parse() {
    const data = this.data;
    if (data.length < 4) throw new Error("HNM too short");
    this.headerSize = u16(data, 0);
    if (this.headerSize > data.length) throw new Error("Not an HNM file (bad header size)");
    const { palette, pos: palEnd } = parsePaletteBlock(data, 2);
    this.palette = palette;
    let pos = palEnd;
    while (pos < this.headerSize && data[pos] === 0xff) pos++;
    const tableSize = this.headerSize - pos;
    if (tableSize >= 4) {
      const n = Math.floor(tableSize / 4);
      for (let i = 0; i < n; i++) {
        this.frameOffsets.push(u32(data, pos));
        pos += 4;
      }
    }
    this.frameCount = this.frameOffsets.length > 1 ? this.frameOffsets.length - 1 : 0;
    if (this.frameCount === 0) throw new Error("Not an HNM file (no frames)");
  }

  decodeFrame(frameIdx: number, framebuf: Uint8Array, palette: Uint8Array): boolean {
    if (frameIdx >= this.frameCount || frameIdx >= this.frameOffsets.length - 1) return false;
    const data = this.data;
    const frameStart = this.frameOffsets[frameIdx] + this.headerSize;
    const frameEnd = this.frameOffsets[frameIdx + 1] + this.headerSize;
    if (frameStart + 2 > data.length) return false;
    let pos = frameStart + 2;
    let hadVideo = false;

    while (pos + 4 <= frameEnd && pos + 4 <= data.length) {
      const tag = u16(data, pos);
      if (tag === 0x6c70) {
        // palette update — merge non-zero entries
        const subSize = u16(data, pos + 2);
        const { palette: np } = parsePaletteBlock(data, pos + 4);
        for (let i = 0; i < 256; i++) {
          const r = np[i * 3];
          const g = np[i * 3 + 1];
          const b = np[i * 3 + 2];
          if (r || g || b) {
            palette[i * 3] = r;
            palette[i * 3 + 1] = g;
            palette[i * 3 + 2] = b;
          }
        }
        if (subSize === 0) break;
        pos += subSize;
      } else if (tag === 0x6473 || tag === 0x6d6d) {
        const subSize = u16(data, pos + 2);
        if (subSize === 0) break;
        pos += subSize;
      } else {
        const b0 = data[pos];
        const b1 = data[pos + 1];
        const w = ((b1 & 0x01) << 8) | b0;
        const flags = b1 & 0xfe;
        const h = data[pos + 2];
        const mode = data[pos + 3];
        const dataPos = pos + 4;
        if (w === 0 || h === 0) break;
        const remaining = frameEnd - dataPos;
        if (flags & 0x02) {
          const frameData = data.subarray(dataPos, dataPos + remaining);
          const cs = frameChecksum(frameData);
          if (cs === 0xab) {
            let decoded: Uint8Array;
            try {
              decoded = hsqDecompress(frameData);
            } catch {
              break;
            }
            if (flags & 0x04) renderFrame(decoded, framebuf, 0, 0, w, h, flags, mode);
            else if (decoded.length >= 4) renderFrame(decoded, framebuf, u16(decoded, 0), u16(decoded, 2), w, h, flags, mode, 4);
          } else if (cs === 0xad) {
            const { output, x, y } = decompressFrameAd(frameData);
            renderFrame(output, framebuf, x, y, w, h, flags, mode);
          } else break;
        } else {
          const raw = data.subarray(dataPos, dataPos + remaining);
          if (flags & 0x04) renderFrame(raw, framebuf, 0, 0, w, h, flags, mode);
          else if (raw.length >= 4) renderFrame(raw, framebuf, u16(raw, 0), u16(raw, 2), w, h, flags, mode, 4);
        }
        hadVideo = true;
        break;
      }
    }
    return hadVideo;
  }

  /** Concatenated 8-bit PCM sound from all 'sd' sub-chunks (~11111 Hz). */
  extractSound(): Uint8Array {
    const out: number[] = [];
    const data = this.data;
    for (let f = 0; f < this.frameCount; f++) {
      const frameStart = this.frameOffsets[f] + this.headerSize;
      const frameEnd = this.frameOffsets[f + 1] + this.headerSize;
      if (frameStart + 2 > data.length) break;
      let pos = frameStart + 2;
      while (pos + 4 <= frameEnd && pos + 4 <= data.length) {
        const tag = u16(data, pos);
        const subSize = u16(data, pos + 2);
        if (tag === 0x6473) {
          const n = subSize - 4;
          if (n > 0 && pos + 4 + n <= data.length) for (let i = 0; i < n; i++) out.push(data[pos + 4 + i]);
        }
        if (subSize === 0 || (tag !== 0x6c70 && tag !== 0x6473 && tag !== 0x6d6d)) break;
        pos += subSize;
      }
    }
    return Uint8Array.from(out);
  }
}

/** Render a paletted framebuffer (64000 bytes) to RGBA for a 320×200 canvas. */
export function framebufToRGBA(framebuf: Uint8Array, palette: Uint8Array): Uint8ClampedArray {
  const out = new Uint8ClampedArray(64000 * 4);
  for (let i = 0; i < 64000; i++) {
    const idx = framebuf[i] * 3;
    const o = i * 4;
    out[o] = palette[idx];
    out[o + 1] = palette[idx + 1];
    out[o + 2] = palette[idx + 2];
    out[o + 3] = 255;
  }
  return out;
}
