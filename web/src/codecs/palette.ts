/**
 * ReDune codecs — VGA palette colour-cycling.
 *
 * Cryo's Dune animates scenes by *colour cycling*: rotating a contiguous range
 * of palette (VGA DAC) entries each frame instead of storing extra frames.
 *
 * GROUND TRUTH (disassembly of the HSQ overlays `DNVGA`/`DN386`, not the main
 * `DNCDPRG.EXE`): the engine has exactly one hardcoded cycle band — DAC indices
 * **0x80–0xBF (64 colours)** — rotated by one slot per frame. The rotate-and-
 * upload routine is at DNVGA 0x0ADC / DN386 0x0AC4; the range immediates
 * (`mov bx,0x80; mov cx,0x40`) at DNVGA 0x0AF7 / DN386 0x0ADF, called from the
 * per-frame screen routine (DNVGA 0x3400 / DN386 0x3405). See
 * `docs/adlib_driver.md`'s companion note and `ENGINE_CYCLE_RANGE` below.
 *
 * `detectCycleRanges` additionally recovers *candidate* ramps heuristically
 * (smooth contiguous colour runs) for authoring/preview; only the 0x80–0xBF
 * band is the one this code path actually animates in-game.
 */
import type { RGB } from "./sprite";

export interface CycleRange {
  /** first palette index in the ramp (inclusive) */
  start: number;
  /** last palette index in the ramp (inclusive) */
  end: number;
}

/**
 * The engine's single hardcoded colour-cycle band, verified from the DNVGA /
 * DN386 overlay disassembly: VGA DAC indices 0x80–0xBF (128–191), 64 entries,
 * rotated one slot per frame. This is authoritative (not a heuristic).
 */
export const ENGINE_CYCLE_RANGE: CycleRange = { start: 0x80, end: 0xbf };

/**
 * The verified engine cycle band, clamped to the indices actually present in
 * `palette`. Returns null if the palette has no entries in 0x80–0xBF.
 */
export function engineCycleRange(palette: Map<number, RGB>): CycleRange | null {
  let lo = -1;
  let hi = -1;
  for (let i = ENGINE_CYCLE_RANGE.start; i <= ENGINE_CYCLE_RANGE.end; i++) {
    if (palette.has(i)) {
      if (lo < 0) lo = i;
      hi = i;
    }
  }
  return lo >= 0 && hi - lo + 1 >= 2 ? { start: lo, end: hi } : null;
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
