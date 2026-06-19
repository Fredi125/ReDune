/**
 * ReDune codecs — Creative Voice File (VOC) sound decoder.
 * Port of tools/sound_decoder.py. Auto-detects HSQ-compressed vs raw VOC.
 * Returns 8-bit unsigned PCM samples + sample rate, ready for WebAudio/WAV.
 */
import { hsqDecompress } from "./compression";

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
