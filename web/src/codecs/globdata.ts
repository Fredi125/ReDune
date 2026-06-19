/**
 * ReDune codecs — GLOBDATA.HSQ polygon-shading gradient tables.
 * Port of parse_gradient_tables in tools/globdata_decoder.py.
 *
 * Part 1 of GLOBDATA is a series of variable-length gradient tables used by the
 * SAL polygon filler (sub_13BE9). Each table: a marker byte (table_len =
 * 256 - marker, markers 0xBF..0xFF) followed by (len-1) palette-index bytes that
 * form a vertical colour ramp. A SAL polygon with subtype S fills its scanlines
 * top->bottom using table (S & 0x7F): row r -> palette index values[min(r,len-1)].
 */
import { isHsq, hsqDecompress } from "./compression";

export interface GradTable {
  offset: number;
  marker: number;
  length: number;
  baseColor: number;
  values: number[];
}

export function parseGradientTables(data: Uint8Array): { tables: GradTable[]; end: number } {
  const tables: GradTable[] = [];
  let i = 0;
  while (i < data.length) {
    const marker = data[i];
    if (marker < 0xbf) break;
    const tableLen = 256 - marker;
    if (tableLen === 1) {
      tables.push({ offset: i, marker, length: 0, baseColor: 0, values: [] });
      i += 1;
      continue;
    }
    if (i + tableLen > data.length) break;
    const values = Array.from(data.subarray(i + 1, i + tableLen));
    tables.push({ offset: i, marker, length: values.length, baseColor: values[0] ?? 0, values });
    i += tableLen;
  }
  return { tables, end: i };
}

/** Load GLOBDATA.HSQ and return the non-empty gradient ramps (indexable by subtype&0x7F). */
export function loadGradientTables(raw: Uint8Array): GradTable[] {
  const data = isHsq(raw) ? hsqDecompress(raw) : raw;
  return parseGradientTables(data).tables.filter((t) => t.length > 0);
}
