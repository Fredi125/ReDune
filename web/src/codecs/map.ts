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
 * Arrakis terrain palette for the globe view: a desert ramp (dark rock → dune
 * sand → pale highlands) rather than the analytic heatmap. The exact in-game
 * globe palette lives in DNCDPRG (sub_1BA75) and isn't published, so this is a
 * plausible planet-surface colouring, not a byte-exact reproduction.
 */
export function planetColor(val: number): [number, number, number] {
  const stops: [number, [number, number, number]][] = [
    [0, [45, 30, 20]], // shadowed rock
    [64, [120, 72, 38]], // red rock
    [128, [196, 146, 84]], // dune sand
    [192, [232, 202, 150]], // bright sand
    [255, [150, 140, 122]], // pale rocky highland
  ];
  let lo = stops[0];
  let hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (val >= stops[i][0] && val <= stops[i + 1][0]) {
      lo = stops[i];
      hi = stops[i + 1];
      break;
    }
  }
  const span = hi[0] - lo[0] || 1;
  const t = (val - lo[0]) / span;
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
