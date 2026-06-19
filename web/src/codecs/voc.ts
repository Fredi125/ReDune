/**
 * ReDune codecs — Creative Voice File (VOC) sound decoder.
 * Port of tools/sound_decoder.py. Auto-detects HSQ-compressed vs raw VOC.
 * Returns 8-bit unsigned PCM samples + sample rate, ready for WebAudio/WAV.
 */
import { hsqCompress, hsqDecompress } from "./compression";

const VOC_MAGIC = "Creative Voice File\x1a";

export function isVoc(d: Uint8Array): boolean {
  if (d.length < 20) return false;
  for (let i = 0; i < 20; i++) if (d[i] !== VOC_MAGIC.charCodeAt(i)) return false;
  return true;
}

export interface VocResult {
  sampleRate: number;
  /** 8-bit unsigned PCM (0x80 = silence midpoint) */
  samples: Uint8Array;
  duration: number;
  soundBlocks: number;
}

export function decodeVoc(raw: Uint8Array): VocResult {
  let data = raw;
  if (!isVoc(data)) {
    try {
      data = hsqDecompress(raw);
    } catch {
      /* leave as-is */
    }
  }
  if (!isVoc(data)) throw new Error("Not a VOC sound file");

  const headerSize = data[20] | (data[21] << 8);
  let pos = headerSize;
  const samples: number[] = [];
  let sampleRate = 0;
  let soundBlocks = 0;

  while (pos < data.length) {
    const bt = data[pos++];
    if (bt === 0x00) break; // terminator
    if (pos + 2 >= data.length) break;
    const blen = data[pos] | (data[pos + 1] << 8) | (data[pos + 2] << 16);
    pos += 3;

    if (bt === 0x01) {
      if (blen < 2) {
        pos += blen;
        continue;
      }
      const srByte = data[pos];
      const rate = srByte < 256 ? Math.floor(1000000 / (256 - srByte)) : 0;
      const n = blen - 2;
      if (sampleRate === 0) sampleRate = rate;
      for (let i = 0; i < n; i++) samples.push(data[pos + 2 + i]); // raw 8-bit PCM
      soundBlocks++;
      pos += blen;
    } else if (bt === 0x03) {
      const slen = blen >= 2 ? data[pos] | (data[pos + 1] << 8) : 0;
      for (let i = 0; i < slen + 1; i++) samples.push(0x80);
      pos += blen;
    } else {
      pos += blen;
    }
  }

  const s = Uint8Array.from(samples);
  return { sampleRate, samples: s, duration: sampleRate > 0 ? s.length / sampleRate : 0, soundBlocks };
}

/**
 * Encode 8-bit unsigned PCM mono samples into a Creative Voice File (VOC):
 * 26-byte header + one type-0x01 PCM8 sound block + terminator. The inverse of
 * decodeVoc for the formats Dune uses.
 */
export function encodeVoc(samples: Uint8Array, sampleRate: number): Uint8Array {
  const rate = Math.max(1, Math.min(255000, Math.round(sampleRate)));
  const srByte = Math.max(0, Math.min(255, 256 - Math.round(1000000 / rate)));
  const n = samples.length;
  const blockLen = n + 2; // sr byte + codec byte + data
  const out: number[] = [];
  for (let i = 0; i < VOC_MAGIC.length; i++) out.push(VOC_MAGIC.charCodeAt(i));
  out.push(0x1a, 0x00); // header size = 26
  out.push(0x0a, 0x01); // version 1.10
  const check = (~0x010a + 0x1234) & 0xffff; // = 0x1129
  out.push(check & 0xff, (check >> 8) & 0xff);
  // sound data block
  out.push(0x01, blockLen & 0xff, (blockLen >> 8) & 0xff, (blockLen >> 16) & 0xff);
  out.push(srByte, 0x00); // sample-rate byte, codec 0 = PCM8
  for (let i = 0; i < n; i++) out.push(samples[i]);
  out.push(0x00); // terminator
  return Uint8Array.from(out);
}

/** Re-compress a VOC into an HSQ container (for SN*.HSQ sound replacement). */
export function encodeVocHsq(samples: Uint8Array, sampleRate: number): Uint8Array {
  return hsqCompress(encodeVoc(samples, sampleRate));
}

function fourcc(d: Uint8Array, o: number): string {
  return String.fromCharCode(d[o], d[o + 1], d[o + 2], d[o + 3]);
}

/**
 * Decode a PCM WAV file to 8-bit unsigned mono samples (for importing a sound to
 * re-encode as VOC). Handles 8/16-bit PCM, mono/stereo (down-mixed).
 */
export function wavToSamples(wav: Uint8Array): { samples: Uint8Array; sampleRate: number } {
  if (wav.length < 44 || fourcc(wav, 0) !== "RIFF" || fourcc(wav, 8) !== "WAVE") throw new Error("Not a WAV file");
  const dv = new DataView(wav.buffer, wav.byteOffset, wav.byteLength);
  let pos = 12;
  let channels = 1;
  let rate = 8000;
  let bits = 8;
  let dataOff = -1;
  let dataLen = 0;
  while (pos + 8 <= wav.length) {
    const id = fourcc(wav, pos);
    const sz = dv.getUint32(pos + 4, true);
    const body = pos + 8;
    if (id === "fmt ") {
      channels = dv.getUint16(body + 2, true) || 1;
      rate = dv.getUint32(body + 4, true) || 8000;
      bits = dv.getUint16(body + 14, true) || 8;
    } else if (id === "data") {
      dataOff = body;
      dataLen = Math.min(sz, wav.length - body);
    }
    pos = body + sz + (sz & 1); // chunks are word-aligned
  }
  if (dataOff < 0) throw new Error("WAV has no data chunk");

  const bytesPerSample = bits >> 3;
  const frame = bytesPerSample * channels;
  const frames = frame > 0 ? Math.floor(dataLen / frame) : 0;
  const out = new Uint8Array(frames);
  for (let i = 0; i < frames; i++) {
    let acc = 0;
    for (let c = 0; c < channels; c++) {
      const so = dataOff + i * frame + c * bytesPerSample;
      if (bits === 8) acc += wav[so]; // already unsigned 0..255
      else acc += ((dv.getInt16(so, true) >> 8) + 128) & 0xff; // 16-bit signed -> 8-bit unsigned
    }
    out[i] = Math.max(0, Math.min(255, Math.round(acc / channels)));
  }
  return { samples: out, sampleRate: rate };
}

/** Build a mono 8-bit PCM WAV file from decoded VOC samples. */
export function vocToWav(v: VocResult): Uint8Array {
  const n = v.samples.length;
  const sr = v.sampleRate || 8000;
  const buf = new Uint8Array(44 + n);
  const dv = new DataView(buf.buffer);
  const str = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) buf[off + i] = s.charCodeAt(i);
  };
  str(0, "RIFF");
  dv.setUint32(4, 36 + n, true);
  str(8, "WAVE");
  str(12, "fmt ");
  dv.setUint32(16, 16, true);
  dv.setUint16(20, 1, true); // PCM
  dv.setUint16(22, 1, true); // mono
  dv.setUint32(24, sr, true);
  dv.setUint32(28, sr, true); // byte rate
  dv.setUint16(32, 1, true); // block align
  dv.setUint16(34, 8, true); // bits/sample
  str(36, "data");
  dv.setUint32(40, n, true);
  buf.set(v.samples, 44);
  return buf;
}
