/**
 * ReDune codecs — MAP.HSQ world-map heatmap renderer.
 * Port of the v1 heatmap in tools/map_decoder.py. The game's true globe
 * projection (via TABLAT) isn't fully reversed yet, so this lays the terrain
 * bytes out row-major and maps each to a fixed low->high colour gradient.
 */
import { hsqDecompress } from "./compression";

export const RES_MAP_SIZE = 0x0c5f9; // 50681
export const MAP_WIDTHS = [200, 304, 320, 400, 500];
export const MAP_DEFAULT_WIDTH = 320;

export function detectMapWidth(size: number): number {
  for (const w of MAP_WIDTHS) if (size % w < 10) return w;
  return MAP_DEFAULT_WIDTH;
}

/** Terrain byte (0x00-0xFF) -> [r,g,b]; matches map_decoder.map_heatmap_color. */
export function heatmapColor(val: number): [number, number, number] {
  if (val < 0x40) {
    const t = val / 0x3f;
    return [0, 0, Math.floor(255 * t)];
  }
  if (val < 0x80) {
    const t = (val - 0x40) / 0x3f;
    return [0, Math.floor(255 * t), Math.floor(255 * (1 - t))];
  }
  if (val < 0xc0) {
    const t = (val - 0x80) / 0x3f;
    return [Math.floor(255 * t), 255, 0];
  }
  const t = (val - 0xc0) / 0x3f;
  if (t < 0.5) {
    const u = t / 0.5;
    return [255, Math.floor(255 * (1 - u)), 0];
  }
  const u = (t - 0.5) / 0.5;
  return [255, Math.floor(255 * u), Math.floor(255 * u)];
}

/**
 * The engine's globe/planet pixel→palette-index map, **verified** from the
 * DN386 VGA overlay's sphere-fill routine (file offset 0x1D1E):
 *
 *   AL = src & 0x0F ;  AH = src & 0x30
 *   if (AH == 0x10 && AL < 8) AL += 0x0C
 *   AL += 0x10
 *
 * i.e. the planet disc is drawn in the fixed low palette **bank 0x10–0x1F** (a
 * few shades reach 0x23 via the special case) — NOT the 0x80–0xBF colour-cycle
 * band, and NOT a 256-level ramp. The fill routine is DN386 @0x1B8C: the disc is
 * centred at screen column 160 / rows 79–80 and filled symmetrically outward,
 * 200-byte source pitch (= GLOBDATA latitude-block size), half-width per row from
 * TABLAT (199·cos lat). Rotation is driven by the *caller* re-projecting the
 * source each frame, not by this primitive. (The project's old `sub_1BA75` /
 * DNCDPRG citation was wrong — DNCDPRG.EXE has no render code; this lives in the
 * DN386 overlay.)
 */
export function planetPaletteIndex(val: number): number {
  let al = val & 0x0f;
  const ah = val & 0x30;
  if (ah === 0x10 && al < 8) al += 0x0c;
  return al + 0x10;
}

/**
 * Approximate RGB for the globe view. The engine indexes the ~16-shade palette
 * bank above; the *actual* RGB of indices 0x10–0x23 is uploaded to the VGA DAC
 * at runtime (not present in the overlay), so we map the verified shade index
 * onto a desert ramp (dark rock → sand → pale highland). Faithful in structure
 * (the real ~16-level banding), approximate in colour.
 */
export function planetColor(val: number): [number, number, number] {
  const idx = planetPaletteIndex(val); // 0x10..0x23
  const shade = Math.max(0, Math.min(19, idx - 0x10)) / 19; // 0..1 across the bank
  const stops: [number, [number, number, number]][] = [
    [0, [45, 30, 20]], // shadowed rock
    [0.25, [120, 72, 38]], // red rock
    [0.5, [196, 146, 84]], // dune sand
    [0.75, [232, 202, 150]], // bright sand
    [1, [150, 140, 122]], // pale rocky highland
  ];
  let lo = stops[0];
  let hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (shade >= stops[i][0] && shade <= stops[i + 1][0]) {
      lo = stops[i];
      hi = stops[i + 1];
      break;
    }
  }
  const span = hi[0] - lo[0] || 1;
  const t = (shade - lo[0]) / span;
  return [
    Math.round(lo[1][0] + (hi[1][0] - lo[1][0]) * t),
    Math.round(lo[1][1] + (hi[1][1] - lo[1][1]) * t),
    Math.round(lo[1][2] + (hi[1][2] - lo[1][2]) * t),
  ];
}

export interface MapImage {
  width: number;
  height: number;
  rgba: Uint8ClampedArray;
}

export function decodeMap(raw: Uint8Array, isRaw = false): Uint8Array {
  return isRaw ? raw : hsqDecompress(raw);
}

export function renderMapRGBA(data: Uint8Array, width?: number): MapImage {
  const w = width || detectMapWidth(data.length);
  const h = Math.ceil(data.length / w);
  const rgba = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) {
    const o = i * 4;
    if (i < data.length) {
      const [r, g, b] = heatmapColor(data[i]);
      rgba[o] = r;
      rgba[o + 1] = g;
      rgba[o + 2] = b;
    }
    rgba[o + 3] = 255;
  }
  return { width: w, height: h, rgba };
}
