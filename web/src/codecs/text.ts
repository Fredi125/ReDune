/**
 * ReDune codecs — string-table reader/writer for PHRASE*.HSQ and COMMAND*.HSQ.
 * Both share the layout: offset table (N uint16 LE, N = first/2) followed by
 * strings delimited by the table; 0xFF acts as a variant separator / terminator.
 *
 * Editing model (lossless round-trip): each string's raw bytes are shown as an
 * editable text where
 *   0xFF       -> "|"        (variant separator)
 *   0x7B "{"   -> "{7B}"     (escaped so it can't collide with a token)
 *   0x7C "|"   -> "{7C}"     (escaped)
 *   byte <0x20 -> "{XX}"     (control byte, hex)
 *   else       -> Latin-1 character
 * editableToBytes() reverses this exactly, so an untouched table re-encodes to
 * byte-identical decompressed data.
 */

import { hsqCompress, hsqDecompress } from "./compression";

function u16(d: Uint8Array, o: number): number {
  return d[o] | (d[o + 1] << 8);
}

export function bytesToEditable(b: Uint8Array): string {
  let s = "";
  for (const x of b) {
    if (x === 0xff) s += "|";
    else if (x === 0x7b) s += "{7B}";
    else if (x === 0x7c) s += "{7C}";
    else if (x < 0x20) s += "{" + x.toString(16).toUpperCase().padStart(2, "0") + "}";
    else s += String.fromCharCode(x); // Latin-1 (0x20..0xFE)
  }
  return s;
}

export function editableToBytes(s: string): Uint8Array {
  const out: number[] = [];
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === "|") {
      out.push(0xff);
      continue;
    }
    if (c === "{") {
      const m = /^\{([0-9A-Fa-f]{2})\}/.exec(s.slice(i, i + 4));
      if (m) {
        out.push(parseInt(m[1], 16));
        i += 3;
        continue;
      }
      out.push(0x7b); // stray '{'
      continue;
    }
    out.push(s.charCodeAt(i) & 0xff); // Latin-1
  }
  return Uint8Array.from(out);
}

export interface TextEntry {
  index: number;
  raw: Uint8Array;
  text: string;
}

export interface TextTable {
  data: Uint8Array;
  count: number;
  offsets: number[];
  entries: TextEntry[];
}

export function loadTextTable(raw: Uint8Array, isRaw = false): TextTable {
  let data: Uint8Array;
  try {
    data = isRaw ? raw : hsqDecompress(raw);
  } catch {
    data = raw;
  }
  if (data.length < 2) throw new Error("text table too short");
  const first = u16(data, 0);
  if (first < 2 || first % 2 !== 0 || first > data.length) throw new Error("Not a string table (bad offset table)");
  const count = first >> 1;
  const offsets: number[] = [];
  for (let i = 0; i < count; i++) {
    if (i * 2 + 1 >= data.length) break;
    offsets.push(u16(data, i * 2));
  }
  const entries: TextEntry[] = [];
  for (let i = 0; i < offsets.length; i++) {
    const end = i + 1 < offsets.length ? offsets[i + 1] : data.length;
    const start = Math.min(offsets[i], data.length);
    const r = data.slice(start, Math.max(start, Math.min(end, data.length)));
    entries.push({ index: i, raw: r, text: bytesToEditable(r) });
  }
  return { data, count, offsets, entries };
}

/** Rebuild the decompressed string-table bytes from (possibly edited) entries. */
export function encodeTextTable(entries: { text: string }[]): Uint8Array {
  const blobs = entries.map((e) => editableToBytes(e.text));
  const tableSize = entries.length * 2;
  const out: number[] = [];
  let pos = tableSize;
  for (const b of blobs) {
    out.push(pos & 0xff, (pos >> 8) & 0xff);
    pos += b.length;
  }
  for (const b of blobs) for (const x of b) out.push(x);
  return Uint8Array.from(out);
}

/** Re-compress an edited table back to an HSQ file ready for download/repack. */
export function exportTextHsq(entries: { text: string }[]): Uint8Array {
  return hsqCompress(encodeTextTable(entries));
}

/** Plain display text (variant separators shown as " | ", control bytes hidden). */
export function displayText(raw: Uint8Array): string {
  let s = "";
  for (const x of raw) {
    if (x === 0xff) s += " | ";
    else if (x >= 0x20) s += String.fromCharCode(x);
  }
  return s.replace(/(\s\|\s)+$/, "").trim();
}
