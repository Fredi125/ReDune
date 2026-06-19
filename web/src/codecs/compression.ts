/**
 * ReDune codecs — compression.
 *
 * Direct TypeScript port of lib/compression.py (Python reference implementation).
 * Works on Uint8Array, no DOM/Node dependencies, so it runs in the browser and
 * under tsx/node for tests.
 *
 *   - HSQ (Cryo LZ77-variant) decompress/compress — game resources (*.HSQ)
 *   - F7 RLE decompress/compress — save files (DUNE*.SAV)
 */

// ===========================================================================
// HSQ DECOMPRESSION
// ===========================================================================

export interface HsqSizes {
  decompSize: number;
  compSize: number;
  checksum: number;
}

/** Read the 6-byte HSQ header without decompressing. */
export function hsqGetSizes(data: Uint8Array): HsqSizes {
  if (data.length < 6) throw new Error("Not an HSQ file (too short)");
  const decompSize = data[0] | (data[1] << 8);
  const checksum = data[2];
  const compSize = data[3] | (data[4] << 8);
  return { decompSize, compSize, checksum };
}

/** True if the buffer looks like a valid HSQ container (header checksum == 0xAB). */
export function isHsq(data: Uint8Array): boolean {
  if (data.length < 6) return false;
  let sum = 0;
  for (let i = 0; i < 6; i++) sum += data[i];
  return (sum & 0xff) === 0xab;
}

/**
 * Decompress HSQ data. Mirrors hsq_decompress() in lib/compression.py:
 * a bitstream LZ77 decoder using a 16-bit queue with an implicit sentinel.
 */
export function hsqDecompress(data: Uint8Array): Uint8Array {
  if (data.length < 6) throw new Error(`HSQ data too short: ${data.length} bytes`);

  const decompSize = data[0] | (data[1] << 8);
  let pos = 6;
  let queue = 0; // 16-bit bit queue; 0 means "needs refill"
  const out: number[] = [];

  const readU8 = (): number => {
    if (pos >= data.length) throw new Error(`HSQ: unexpected end at offset ${pos}`);
    return data[pos++];
  };
  const readU16 = (): number => {
    if (pos + 1 >= data.length) throw new Error(`HSQ: unexpected end at offset ${pos}`);
    const v = data[pos] | (data[pos + 1] << 8);
    pos += 2;
    return v;
  };
  const getBit = (): number => {
    let bit = queue & 1;
    queue >>= 1;
    if (queue === 0) {
      queue = readU16();
      bit = queue & 1;
      queue = 0x8000 | (queue >> 1);
    }
    return bit;
  };

  for (;;) {
    if (getBit() !== 0) {
      // Literal byte
      if (out.length >= decompSize) break;
      out.push(readU8());
    } else if (getBit() !== 0) {
      // Long back-reference
      const word = readU16();
      let count = word & 0x07;
      const offset = (word >> 3) - 8192; // signed negative offset
      if (count === 0) count = readU8();
      if (count === 0) break; // EOF
      const dst = out.length;
      for (let i = 0; i < count + 2; i++) out.push(out[dst + offset + i]);
    } else {
      // Short back-reference
      const b0 = getBit();
      const b1 = getBit();
      const count = 2 * b0 + b1; // 0-3
      const offset = readU8() - 256; // signed negative offset
      const dst = out.length;
      for (let i = 0; i < count + 2; i++) out.push(out[dst + offset + i]);
    }
  }

  return Uint8Array.from(out.slice(0, decompSize));
}

// ===========================================================================
// HSQ COMPRESSION
// ===========================================================================

type Cmd =
  | { t: "literal"; b: number }
  | { t: "short"; countBits: number; offsetByte: number }
  | { t: "long"; word: number }
  | { t: "long_ext"; word: number; extra: number };

class BitWriter {
  stream: number[] = [];
  private wordBits: number[] = [];
  private wordPos = -1;

  private startWord() {
    this.wordPos = this.stream.length;
    this.stream.push(0, 0); // placeholder
    this.wordBits = [];
  }
  writeBit(b: number) {
    if (this.wordPos < 0 || this.wordBits.length >= 16) {
      this.flushWord();
      this.startWord();
    }
    this.wordBits.push(b & 1);
  }
  writeByte(b: number) {
    this.stream.push(b & 0xff);
  }
  writeWord(w: number) {
    this.stream.push(w & 0xff, (w >> 8) & 0xff);
  }
  private flushWord() {
    if (this.wordPos < 0) return;
    while (this.wordBits.length < 16) this.wordBits.push(0);
    let word = 0;
    for (let i = 0; i < 16; i++) word |= (this.wordBits[i] & 1) << i;
    this.stream[this.wordPos] = word & 0xff;
    this.stream[this.wordPos + 1] = (word >> 8) & 0xff;
    this.wordBits = [];
    this.wordPos = -1;
  }
  finish(): number[] {
    if (this.wordPos >= 0) this.flushWord();
    return this.stream;
  }
}

function buildHeader(decompSize: number, compSize: number): number[] {
  const hdr = [0, 0, 0, 0, 0, 0];
  hdr[0] = decompSize & 0xff;
  hdr[1] = (decompSize >> 8) & 0xff;
  hdr[2] = 0x00;
  hdr[3] = compSize & 0xff;
  hdr[4] = (compSize >> 8) & 0xff;
  hdr[5] = (0xab - hdr[0] - hdr[1] - hdr[2] - hdr[3] - hdr[4]) & 0xff;
  return hdr;
}

/**
 * Compress data with HSQ encoding (greedy hash-chain LZ77).
 * Output is compatible with hsqDecompress(). Mirrors hsq_compress() in Python.
 */
export function hsqCompress(data: Uint8Array): Uint8Array {
  const srcLen = data.length;
  if (srcLen === 0) {
    const eofBits = (0 << 0) | (1 << 1);
    const body = [eofBits & 0xff, (eofBits >> 8) & 0xff, 0, 0, 0];
    const hdr = buildHeader(0, 6 + body.length);
    return Uint8Array.from([...hdr, ...body]);
  }

  const HASH_SIZE = 1 << 15;
  const HASH_MASK = HASH_SIZE - 1;
  const MAX_CHAIN = 64;
  const head = new Int32Array(HASH_SIZE).fill(-1);
  const prev = new Int32Array(srcLen);

  const hash3 = (p: number): number => {
    if (p + 2 >= srcLen) return 0;
    return ((data[p] << 10) ^ (data[p + 1] << 5) ^ data[p + 2]) & HASH_MASK;
  };

  const insert = (p: number) => {
    if (p + 2 < srcLen) {
      const h = hash3(p);
      prev[p] = head[h] >= 0 ? head[h] : p;
      head[h] = p;
    }
  };

  const commands: Cmd[] = [];
  let pos = 0;

  while (pos < srcLen) {
    let bestLen = 0;
    let bestOff = 0;
    const maxLen = Math.min(srcLen - pos, 257);

    if (pos + 2 < srcLen) {
      const h = hash3(pos);
      let matchPos = head[h];
      let chainCount = 0;
      const minPos = Math.max(0, pos - 8192);
      while (matchPos >= minPos && chainCount < MAX_CHAIN) {
        let ml = 0;
        while (ml < maxLen && data[pos + ml] === data[matchPos + ml]) ml++;
        if (ml > bestLen) {
          bestLen = ml;
          bestOff = pos - matchPos;
          if (bestLen >= maxLen) break;
        }
        chainCount++;
        const nextPos = prev[matchPos];
        if (nextPos >= matchPos) break;
        matchPos = nextPos;
      }
      prev[pos] = head[h] >= 0 ? head[h] : pos;
      head[h] = pos;
    }

    if (bestOff <= 256 && bestLen >= 2) {
      const useLen = Math.min(bestLen, 5);
      const countBits = useLen - 2;
      const offsetByte = (-bestOff) & 0xff;
      commands.push({ t: "short", countBits, offsetByte });
      for (let j = 1; j < useLen; j++) insert(pos + j);
      pos += useLen;
    } else if (bestLen >= 3) {
      const offset13 = ((-bestOff) + 8192) & 0x1fff;
      const copyCount = bestLen - 2;
      if (copyCount >= 1 && copyCount <= 7) {
        commands.push({ t: "long", word: (offset13 << 3) | copyCount });
      } else {
        commands.push({ t: "long_ext", word: (offset13 << 3) | 0, extra: copyCount & 0xff });
      }
      for (let j = 1; j < bestLen; j++) insert(pos + j);
      pos += bestLen;
    } else {
      commands.push({ t: "literal", b: data[pos] });
      pos += 1;
    }
  }

  commands.push({ t: "long_ext", word: 0, extra: 0 }); // EOF

  const w = new BitWriter();
  for (const cmd of commands) {
    if (cmd.t === "literal") {
      w.writeBit(1);
      w.writeByte(cmd.b);
    } else if (cmd.t === "short") {
      w.writeBit(0);
      w.writeBit(0);
      w.writeBit((cmd.countBits >> 1) & 1);
      w.writeBit(cmd.countBits & 1);
      w.writeByte(cmd.offsetByte);
    } else if (cmd.t === "long") {
      w.writeBit(0);
      w.writeBit(1);
      w.writeWord(cmd.word);
    } else {
      w.writeBit(0);
      w.writeBit(1);
      w.writeWord(cmd.word);
      w.writeByte(cmd.extra);
    }
  }

  const body = w.finish();
  const hdr = buildHeader(srcLen, 6 + body.length);
  return Uint8Array.from([...hdr, ...body]);
}

// ===========================================================================
// F7 RLE (save files)
// ===========================================================================

/** Decompress F7 RLE save data. Mirrors f7_decompress() in Python. */
export function f7Decompress(data: Uint8Array): Uint8Array {
  const out: number[] = [];
  let i = 0;
  const end = data.length - 3; // 3-byte lookahead

  while (i <= end) {
    const b0 = data[i];
    const b1 = data[i + 1];
    const b2 = data[i + 2];

    if (b0 === 0xf7 && b1 === 0x01 && b2 === 0xf7) {
      out.push(0xf7);
      i += 3;
    } else if (b0 === 0xf7 && b1 > 2) {
      for (let k = 0; k < b1; k++) out.push(b2);
      i += 3;
    } else {
      out.push(b0);
      if (i === end) {
        out.push(b1);
        out.push(b2);
      }
      i += 1;
    }
  }
  while (i < data.length) out.push(data[i++]);
  return Uint8Array.from(out);
}

/** Compress data with F7 RLE encoding. Mirrors f7_compress() in Python. */
export function f7Compress(data: Uint8Array): Uint8Array {
  const out: number[] = [];
  let i = 0;
  while (i < data.length) {
    const b = data[i];
    if (b === 0xf7) {
      out.push(0xf7, 0x01, 0xf7);
      i += 1;
      continue;
    }
    let run = 1;
    while (i + run < data.length && data[i + run] === b && run < 255) run++;
    if (run > 3) {
      out.push(0xf7, run, b);
      i += run;
    } else {
      out.push(b);
      i += 1;
    }
  }
  return Uint8Array.from(out);
}
