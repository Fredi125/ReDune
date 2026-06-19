/**
 * ReDune codecs — DUNE.DAT master-archive parser + builder.
 * Port of tools/dat_decoder.py (parse_dat_header / build_dat).
 *
 * Layout:
 *   header (64KB / 0x10000):
 *     uint16 LE magic (0x0A3D for CD v3.7)
 *     entries of 25 bytes: name[16] (null-padded ASCII) + int32 size + int32 offset + byte flag
 *     terminated by an entry whose first name byte is 0
 *   data region (after header): each file's bytes, padded to a 16-byte boundary
 *   between files (no padding after the last file). Entry offset is absolute.
 */
import { isHsq } from "./compression";

export const DAT_MAGIC = 0x0a3d;
export const DAT_HEADER_SIZE = 0x10000;
export const DAT_ENTRY_SIZE = 25;
export const DAT_MAX_NAME = 15;
export const DAT_MAX_ENTRIES = Math.floor((DAT_HEADER_SIZE - 3) / DAT_ENTRY_SIZE);

export interface DatEntry {
  name: string;
  size: number;
  offset: number;
  flag: number;
}

export interface DatFile {
  magic: number;
  entries: DatEntry[];
  data: Uint8Array;
}

export interface BuildFile {
  name: string;
  data: Uint8Array;
  flag: number;
}

function readCStr(d: Uint8Array, off: number, max: number): string {
  let s = "";
  for (let i = 0; i < max; i++) {
    const c = d[off + i];
    if (c === 0) break;
    s += String.fromCharCode(c);
  }
  return s;
}

function pad16(len: number): number {
  const r = len % 16;
  return r === 0 ? 0 : 16 - r;
}

export function parseDat(data: Uint8Array): DatFile {
  if (data.length < DAT_HEADER_SIZE) throw new Error(`Too small for a DUNE.DAT header (need ${DAT_HEADER_SIZE} bytes)`);
  const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const magic = dv.getUint16(0, true);
  const entries: DatEntry[] = [];
  let pos = 2;
  while (pos + DAT_ENTRY_SIZE <= DAT_HEADER_SIZE) {
    if (data[pos] === 0) break;
    entries.push({
      name: readCStr(data, pos, 16),
      size: dv.getInt32(pos + 16, true),
      offset: dv.getInt32(pos + 20, true),
      flag: data[pos + 24],
    });
    pos += DAT_ENTRY_SIZE;
  }
  return { magic, entries, data };
}

export function extractFile(dat: DatFile, e: DatEntry): Uint8Array {
  return dat.data.subarray(e.offset, e.offset + e.size);
}

export function entryIsHsq(dat: DatFile, e: DatEntry): boolean {
  return isHsq(extractFile(dat, e));
}

/** Build a DUNE.DAT from a list of files. Byte-identical with build_dat. */
export function buildDat(files: BuildFile[], magic = DAT_MAGIC): Uint8Array {
  if (files.length > DAT_MAX_ENTRIES) throw new Error(`Too many files: ${files.length} (max ${DAT_MAX_ENTRIES})`);
  for (const f of files) if (f.name.length > DAT_MAX_NAME) throw new Error(`Filename too long (max ${DAT_MAX_NAME}): ${f.name}`);

  let dataLen = 0;
  for (let i = 0; i < files.length; i++) {
    dataLen += files[i].data.length;
    if (i < files.length - 1) dataLen += pad16(files[i].data.length);
  }
  const out = new Uint8Array(DAT_HEADER_SIZE + dataLen);
  const dv = new DataView(out.buffer);
  dv.setUint16(0, magic, true);

  let pos = 2;
  let dataOffset = DAT_HEADER_SIZE;
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    for (let k = 0; k < f.name.length; k++) out[pos + k] = f.name.charCodeAt(k) & 0xff;
    dv.setInt32(pos + 16, f.data.length, true);
    dv.setInt32(pos + 20, dataOffset, true);
    out[pos + 24] = f.flag & 0xff;
    dataOffset += f.data.length;
    dataOffset = (dataOffset + 15) & ~15;
    pos += DAT_ENTRY_SIZE;
  }

  let wpos = DAT_HEADER_SIZE;
  for (let i = 0; i < files.length; i++) {
    out.set(files[i].data, wpos);
    wpos += files[i].data.length;
    if (i < files.length - 1) wpos += pad16(files[i].data.length);
  }
  return out;
}

/** Rebuild an archive, substituting any entries present in `replacements`. */
export function rebuildDat(dat: DatFile, replacements: Map<string, Uint8Array>): Uint8Array {
  const files: BuildFile[] = dat.entries.map((e) => ({
    name: e.name,
    data: replacements.get(e.name) ?? extractFile(dat, e),
    flag: e.flag,
  }));
  return buildDat(files, dat.magic);
}
