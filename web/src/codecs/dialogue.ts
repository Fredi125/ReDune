/**
 * ReDune codecs — DIALOGUE.HSQ script-table parser.
 * Port of tools/dialogue_decompiler.py / dialogue_browser.py.
 *
 * DIALOGUE.HSQ is a fixed 4-byte record table (NOT a VM). Each entry is a list
 * of records (terminated by 0xFFFF). Each record gates a PHRASE string on a
 * CONDIT condition:
 *   byte0: bit7=spoken, bit6=repeatable, bits3-0=action code
 *   byte1: NPC id (low byte of CONDIT index)
 *   byte2: bits7-6=cond_type, bits3-2=menu flag, bits1-0=phrase hi
 *   byte3: phrase id low byte
 * CONDIT index = cond_type*256 + byte1 ; phrase id = ((byte2&3)<<8) | byte3
 */
import { hsqCompress, hsqDecompress } from "./compression";

export interface DialogueRecord {
  spoken: boolean;
  repeatable: boolean;
  actionCode: number;
  npcId: number;
  condType: number;
  conditIdx: number;
  menuFlag: number;
  phraseIdx: number;
  raw: [number, number, number, number];
}

export interface DialogueEntry {
  entry: number;
  offset: number;
  records: DialogueRecord[];
}

export interface DialogueFile {
  data: Uint8Array;
  entryCount: number;
  offsets: number[];
  entries: DialogueEntry[]; // all entries (including empty)
}

function u16(d: Uint8Array, o: number): number {
  return d[o] | (d[o + 1] << 8);
}

export function decodeRecord(b0: number, b1: number, b2: number, b3: number): DialogueRecord {
  const condType = (b2 >> 6) & 0x03;
  return {
    spoken: !!(b0 & 0x80),
    repeatable: !!(b0 & 0x40),
    actionCode: b0 & 0x0f,
    npcId: b1,
    condType,
    conditIdx: condType * 256 + b1,
    menuFlag: (b2 >> 2) & 0x03,
    phraseIdx: ((b2 & 0x03) << 8) | b3,
    raw: [b0, b1, b2, b3],
  };
}

export function parseEntry(data: Uint8Array, start: number): DialogueRecord[] {
  const records: DialogueRecord[] = [];
  let pos = start;
  while (pos + 1 < data.length) {
    if (u16(data, pos) === 0xffff) break;
    if (pos + 3 >= data.length) break;
    records.push(decodeRecord(data[pos], data[pos + 1], data[pos + 2], data[pos + 3]));
    pos += 4;
  }
  return records;
}

export function loadDialogue(raw: Uint8Array, isRaw = false): DialogueFile {
  let data: Uint8Array;
  try {
    data = isRaw ? raw : hsqDecompress(raw);
  } catch {
    data = raw;
  }
  if (data.length < 2) throw new Error("DIALOGUE file too short");
  const first = u16(data, 0);
  if (first < 2 || first % 2 !== 0) throw new Error("Not a DIALOGUE table");
  const entryCount = first >> 1;
  const offsets: number[] = [];
  for (let i = 0; i < entryCount; i++) {
    if (i * 2 + 1 >= data.length) break;
    offsets.push(u16(data, i * 2));
  }
  const entries: DialogueEntry[] = offsets.map((off, i) => ({ entry: i, offset: off, records: parseEntry(data, off) }));
  return { data, entryCount, offsets, entries };
}

/** Recompute a record's decoded fields from its 4 raw bytes (after an edit). */
export function refreshRecord(r: DialogueRecord): void {
  const [b0, b1, b2, b3] = r.raw;
  const fresh = decodeRecord(b0, b1, b2, b3);
  Object.assign(r, fresh);
}

/**
 * Encode the dialogue table back to bytes (rebuilds the offset table; each entry
 * = its 4-byte records followed by an 0xFFFF terminator). Byte-identical to the
 * decompressed original for an unedited table.
 */
export function encodeDialogue(entries: DialogueEntry[]): Uint8Array {
  const blobs = entries.map((e) => {
    const b: number[] = [];
    for (const r of e.records) b.push(r.raw[0] & 0xff, r.raw[1] & 0xff, r.raw[2] & 0xff, r.raw[3] & 0xff);
    b.push(0xff, 0xff);
    return b;
  });
  const out: number[] = [];
  let pos = entries.length * 2;
  const offs: number[] = [];
  for (const blob of blobs) {
    offs.push(pos);
    pos += blob.length;
  }
  for (const off of offs) out.push(off & 0xff, (off >> 8) & 0xff);
  for (const blob of blobs) for (const x of blob) out.push(x);
  return Uint8Array.from(out);
}

/** Re-compress an edited dialogue table into a working DIALOGUE.HSQ. */
export function exportDialogueHsq(entries: DialogueEntry[]): Uint8Array {
  return hsqCompress(encodeDialogue(entries));
}
