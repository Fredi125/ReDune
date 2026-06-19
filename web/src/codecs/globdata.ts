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

// Globe projection scanlines (Part 2): 64 latitude blocks × 200 bytes,
// each = 98-byte longitude ramp (screen-x → longitude) + sep + terrain/shade bytes.
const GLOBE_PREFIX = 422;
const GLOBE_BLOCK = 200;
const GLOBE_RAMP = 98;
const GLOBE_COUNT = 64;

export interface GlobeScanline {
  index: number;
  ramp: number[];
  rampMax: number;
  terrain: number[];
}

export function parseGlobe(data: Uint8Array): GlobeScanline[] {
  const { end } = parseGradientTables(data);
  const first = end + GLOBE_PREFIX;
  const out: GlobeScanline[] = [];
  for (let b = 0; b < GLOBE_COUNT; b++) {
    const start = first + b * GLOBE_BLOCK;
    if (start + GLOBE_BLOCK > data.length) break;
    const ramp = Array.from(data.subarray(start, start + GLOBE_RAMP));
    const terrain = Array.from(data.subarray(start + GLOBE_RAMP + 1, start + GLOBE_BLOCK));
    while (terrain.length && terrain[terrain.length - 1] === 0) terrain.pop();
    out.push({ index: b, ramp, rampMax: ramp.length ? Math.max(...ramp) : 0, terrain });
  }
  return out;
}

export function loadGlobe(raw: Uint8Array): GlobeScanline[] {
  const data = isHsq(raw) ? hsqDecompress(raw) : raw;
  return parseGlobe(data);
}
