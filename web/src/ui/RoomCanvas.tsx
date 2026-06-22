import { useEffect, useRef } from "react";
import { decodeSprite, spriteToRGBA, type RGB, type SpriteFile } from "../codecs/sprite";
import type { SalSection } from "../codecs/sal";
import type { GradTable } from "../codecs/globdata";

/** Pre-render every sprite of the decoration sheet to its own canvas (alpha-keyed). */
export function buildSpriteCanvases(sf: SpriteFile): (HTMLCanvasElement | null)[] {
  const out: (HTMLCanvasElement | null)[] = [];
  for (let i = 0; i < sf.count; i++) {
    let s;
    try {
      s = decodeSprite(sf.data, i);
    } catch {
      out.push(null);
      continue;
    }
    if (s.width === 0 || s.height === 0) {
      out.push(null);
      continue;
    }
    const c = document.createElement("canvas");
    c.width = s.width;
    c.height = s.height;
    const ctx = c.getContext("2d");
    if (!ctx) {
      out.push(null);
      continue;
    }
    const img = ctx.createImageData(s.width, s.height);
    img.data.set(spriteToRGBA(s, sf.palette, false));
    ctx.putImageData(img, 0, 0);
    out.push(c);
  }
  return out;
}

function hexToRgb(s: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(s.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

type PixelSink = (x: number, y: number, idx: number) => void;
type PolyCmd = {
  polyType: number;
  polySubtype: number;
  xOffset: number;
  yOffset: number;
  initX: number;
  initY: number;
  verticesPass1: [number, number][];
  verticesPass2: [number, number][];
};

/**
 * The real DNCDPRG `SAL_polygon` fill (ground-truthed from the disasm): a planar
 * 8.8 fixed-point gradient — colour = `(polySubtype<<8 + Δx·xOffset + Δy·yOffset) >> 8`
 * where xOffset/yOffset are the already-×16 slopes (per pixel / per scanline),
 * seeded at each scanline's left edge — plus an optional 2-bit Galois-LFSR
 * ordered-dither stipple over 4 adjacent indices, applied ONLY when
 * `polyType & 0x3E` (PALACE polys are flat; SIET dithers). Colours are raw
 * palette indices (the room scene palette, mostly the 0x80–0xBF cycling band) —
 * NOT a GLOBDATA gradient table (that's the globe renderer).
 */
function fillPolygon(cmd: PolyCmd, put: PixelSink) {
  const pts: [number, number][] = [[cmd.initX, cmd.initY], ...cmd.verticesPass1, ...[...cmd.verticesPass2].reverse()];
  if (pts.length < 3) return;
  let top = Infinity;
  let bot = -Infinity;
  for (const p of pts) {
    if (p[1] < top) top = p[1];
    if (p[1] > bot) bot = p[1];
  }
  const yTop = Math.floor(top);
  const dither = (cmd.polyType & 0x3e) !== 0;
  const tap = ((cmd.polyType & 0x3e) << 8) | 2;
  let lfsr = 1;
  const base = (cmd.polySubtype & 0xff) << 8;
  const yStart = Math.max(0, yTop);
  const yEnd = Math.min(199, Math.ceil(bot));
  for (let y = yStart; y <= yEnd; y++) {
    const xs: number[] = [];
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i];
      const b = pts[(i + 1) % pts.length];
      const ya = a[1];
      const yb = b[1];
      if ((ya <= y && yb > y) || (yb <= y && ya > y)) {
        xs.push(a[0] + ((y - ya) / (yb - ya)) * (b[0] - a[0]));
      }
    }
    if (xs.length < 2) continue;
    xs.sort((p, q) => p - q);
    const scanPhase = base + (y - yTop) * cmd.yOffset; // phase reseeds at each scanline's left edge
    for (let k = 0; k + 1 < xs.length; k += 2) {
      const lx = Math.max(0, Math.ceil(xs[k]));
      const rx = Math.min(319, Math.floor(xs[k + 1]));
      let phase = scanPhase;
      for (let x = lx; x <= rx; x++) {
        let color = (phase >> 8) & 0xff;
        if (dither) {
          const carry = lfsr & 1;
          lfsr >>= 1;
          if (carry) lfsr ^= tap;
          color = (color + ((lfsr & 3) - 1)) & 0xff;
        }
        put(x, y, color);
        phase += cmd.xOffset;
      }
    }
  }
}

/** Bresenham line (the SAL "rect_fill" command is actually a solid line). */
function drawLine(x0: number, y0: number, x1: number, y1: number, color: number, put: PixelSink) {
  x0 |= 0;
  y0 |= 0;
  x1 |= 0;
  y1 |= 0;
  const dx = Math.abs(x1 - x0);
  const dy = Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx - dy;
  for (;;) {
    put(x0, y0, color);
    if (x0 === x1 && y0 === y1) break;
    const e2 = 2 * err;
    if (e2 > -dy) {
      err -= dy;
      x0 += sx;
    }
    if (e2 < dx) {
      err += dx;
      y0 += sy;
    }
  }
}

/** Composite one SAL room section (gradient polygons, line fills, decoration sprites). */
export function RoomCanvas(props: {
  section: SalSection;
  sprites: (HTMLCanvasElement | null)[] | null;
  palette: Map<number, RGB> | null;
  gradTables: GradTable[] | null;
  scale: number;
  show: { sprites: boolean; polys: boolean; rects: boolean };
  bg: string;
  rev: number;
  filter?: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const W = 320;
  const H = 200;

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    c.width = W;
    c.height = H;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;

    // Polygons + line fills go into an ImageData (per-pixel, so the planar
    // gradient + LFSR dither are faithful); sprites are composited on top.
    const img = ctx.createImageData(W, H);
    const data = img.data;
    const bg = hexToRgb(props.bg) ?? [16, 16, 24];
    for (let i = 0; i < W * H; i++) {
      data[i * 4] = bg[0];
      data[i * 4 + 1] = bg[1];
      data[i * 4 + 2] = bg[2];
      data[i * 4 + 3] = 255;
    }
    const pal = props.palette;
    const put: PixelSink = (x, y, idx) => {
      if (x < 0 || x >= W || y < 0 || y >= H) return;
      const o = (y * W + x) * 4;
      const rgb = pal?.get(idx & 0xff);
      if (rgb) {
        data[o] = rgb[0];
        data[o + 1] = rgb[1];
        data[o + 2] = rgb[2];
      } else {
        data[o] = data[o + 1] = data[o + 2] = idx & 0xff; // grayscale fallback
      }
      data[o + 3] = 255;
    };

    for (const cmd of props.section.commands) {
      if (cmd.type === "polygon" && props.show.polys) {
        fillPolygon(cmd, put);
      } else if (cmd.type === "rect_fill" && props.show.rects) {
        drawLine(cmd.x1, cmd.y1, cmd.x2, cmd.y2, cmd.header & 0xff, put);
      }
    }
    ctx.putImageData(img, 0, 0);

    if (props.show.sprites && props.sprites) {
      for (const cmd of props.section.commands) {
        if (cmd.type === "sprite") {
          const sc = props.sprites[cmd.spriteIndex];
          if (sc) ctx.drawImage(sc, cmd.x, cmd.y);
        }
      }
    }
  }, [props.section, props.sprites, props.palette, props.show, props.bg, props.rev]);

  return (
    <canvas
      ref={ref}
      className="pixel"
      style={{ width: W * props.scale, height: H * props.scale, border: "1px solid var(--border)", background: props.bg, filter: props.filter ?? "none" }}
    />
  );
}
