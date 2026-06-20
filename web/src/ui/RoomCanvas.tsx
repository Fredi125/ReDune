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

/** Composite one SAL room section (rect fills, gradient polygons, decoration sprites). */
export function RoomCanvas(props: {
  section: SalSection;
  sprites: (HTMLCanvasElement | null)[] | null;
  palette: Map<number, RGB> | null;
  gradTables: GradTable[] | null;
  scale: number;
  show: { sprites: boolean; polys: boolean; rects: boolean };
  bg: string;
  rev: number;
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
    ctx.fillStyle = props.bg;
    ctx.fillRect(0, 0, W, H);

    const palRgb = (idx: number, fallback: string) => {
      const col = props.palette?.get(idx);
      return col ? `${col[0]},${col[1]},${col[2]}` : fallback;
    };

    for (const cmd of props.section.commands) {
      if (cmd.type === "rect_fill" && props.show.rects) {
        ctx.fillStyle = `rgb(${palRgb(cmd.header & 0xff, "60,60,70")})`;
        const x = Math.min(cmd.x1, cmd.x2);
        const y = Math.min(cmd.y1, cmd.y2);
        ctx.fillRect(x, y, Math.abs(cmd.x2 - cmd.x1), Math.abs(cmd.y2 - cmd.y1));
      } else if (cmd.type === "polygon" && props.show.polys) {
        // Close the shape: init + pass1 (down one edge) + pass2 reversed (up the other).
        const pts: [number, number][] = [[cmd.initX, cmd.initY], ...cmd.verticesPass1, ...[...cmd.verticesPass2].reverse()];
        if (pts.length >= 3) {
          let yTop = Infinity;
          let yBot = -Infinity;
          for (const p of pts) {
            if (p[1] < yTop) yTop = p[1];
            if (p[1] > yBot) yBot = p[1];
          }
          const path = new Path2D();
          path.moveTo(pts[0][0], pts[0][1]);
          for (let k = 1; k < pts.length; k++) path.lineTo(pts[k][0], pts[k][1]);
          path.closePath();
          const table = props.gradTables && (cmd.polySubtype & 0x7f) < props.gradTables.length ? props.gradTables[cmd.polySubtype & 0x7f] : null;
          const span = Math.max(1, yBot - yTop);
          ctx.save();
          ctx.clip(path);
          // Fill scanline-by-scanline with the vertical gradient (authentic when
          // GLOBDATA + the room palette are loaded; approximated otherwise).
          for (let y = Math.max(0, yTop); y <= Math.min(H - 1, yBot); y++) {
            let col: string;
            if (table) {
              const idx = table.values[Math.min(y - yTop, table.length - 1)] ?? 0;
              const rgb = props.palette?.get(idx);
              col = rgb ? `rgb(${rgb[0]},${rgb[1]},${rgb[2]})` : `rgb(${idx},${idx},${idx})`;
            } else {
              const t = (y - yTop) / span;
              const base = props.palette?.get(cmd.polySubtype & 0x3f);
              if (base) {
                const f = 0.55 + 0.45 * t;
                col = `rgb(${(base[0] * f) | 0},${(base[1] * f) | 0},${(base[2] * f) | 0})`;
              } else {
                col = `hsl(${(cmd.polySubtype * 7) % 360} 45% ${(18 + t * 34).toFixed(1)}%)`;
              }
            }
            ctx.fillStyle = col;
            ctx.fillRect(0, y, W, 1);
          }
          ctx.restore();
        }
      } else if (cmd.type === "sprite" && props.show.sprites && props.sprites) {
        const sc = props.sprites[cmd.spriteIndex];
        if (sc) ctx.drawImage(sc, cmd.x, cmd.y);
      }
    }
  }, [props.section, props.sprites, props.palette, props.gradTables, props.show, props.bg, props.rev]);

  return (
    <canvas
      ref={ref}
      className="pixel"
      style={{ width: W * props.scale, height: H * props.scale, border: "1px solid var(--border)", background: props.bg }}
    />
  );
}
