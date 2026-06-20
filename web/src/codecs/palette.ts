/**
 * ReDune codecs — VGA palette colour-cycling.
 *
 * Cryo's Dune animates several scenes by *colour cycling*: rotating a contiguous
 * range of palette entries each tick (shimmering spice, water, sky gradients,
 * twinkling stars) instead of storing extra frames. The exact ranges the engine
 * cycles live in DNCDPRG.EXE, not in any shipped data file, so this module
 * recovers plausible *candidate* ranges heuristically (smooth, contiguous colour
 * ramps) and applies the rotation — enough to preview/author the effect.
 */
import type { RGB } from "./sprite";

export interface CycleRange {
  /** first palette index in the ramp (inclusive) */
  start: number;
  /** last palette index in the ramp (inclusive) */
  end: number;
}

function dist2(a: RGB, b: RGB): number {
  const dr = a[0] - b[0];
  const dg = a[1] - b[1];
  const db = a[2] - b[2];
  return dr * dr + dg * dg + db * db;
}

/**
 * Find candidate colour-cycle ranges: maximal runs of consecutive palette
 * indices whose neighbouring colours are *related but distinct* (a smooth ramp),
 * at least `minLen` entries long. These are the runs Cryo-style engines rotate
 * for shimmer effects.
 */
export function detectCycleRanges(palette: Map<number, RGB>, minLen = 4): CycleRange[] {
  const idxs = [...palette.keys()].sort((a, b) => a - b);
  const ranges: CycleRange[] = [];
  const NEAR = 130 * 130; // related colours (euclidean²) — ramp continues
  const SAME = 4; // identical colours don't form a visible ramp

  let runStart = -1;
  let prev = -1;
  const flush = (end: number) => {
    if (runStart >= 0 && end - runStart + 1 >= minLen) ranges.push({ start: runStart, end });
    runStart = -1;
  };

  for (const i of idxs) {
    const c = palette.get(i)!;
    if (prev >= 0 && prev === i - 1) {
      const pc = palette.get(prev)!;
      const d = dist2(pc, c);
      if (d <= NEAR && d > SAME) {
        if (runStart < 0) runStart = prev;
      } else {
        flush(prev);
      }
    } else {
      flush(prev);
    }
    prev = i;
  }
  flush(prev);
  return ranges;
}

/**
 * Return a new palette with each active range rotated by `step` entries
 * (wrapping within the range). The base palette is left unmodified.
 */
export function rotatePalette(base: Map<number, RGB>, ranges: CycleRange[], step: number): Map<number, RGB> {
  if (ranges.length === 0 || step === 0) return base;
  const out = new Map(base);
  for (const r of ranges) {
    const len = r.end - r.start + 1;
    if (len < 2) continue;
    const colors: RGB[] = [];
    for (let i = r.start; i <= r.end; i++) {
      const c = base.get(i);
      if (!c) {
        colors.length = 0;
        break;
      }
      colors.push(c);
    }
    if (colors.length !== len) continue;
    const s = ((step % len) + len) % len;
    for (let i = 0; i < len; i++) out.set(r.start + i, colors[(i + s) % len]);
  }
  return out;
}
