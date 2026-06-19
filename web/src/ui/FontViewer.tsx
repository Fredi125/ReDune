import { useEffect, useRef, useState } from "react";
import { decodeDnchar, FONT_HEIGHT, glyphPixel, type Glyph } from "../codecs/font";
import { LoadBar, Panel } from "./shared";

function Atlas({ glyphs, scale, color }: { glyphs: Glyph[]; scale: number; color: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const cols = 16;
    const rows = 16;
    const cw = 8;
    const pad = 1;
    const W = cols * (cw + pad) + pad;
    const H = rows * (FONT_HEIGHT + pad) + pad;
    c.width = W;
    c.height = H;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#0d0b08";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = color;
    for (let i = 0; i < 256; i++) {
      const gx = pad + (i % cols) * (cw + pad);
      const gy = pad + Math.floor(i / cols) * (FONT_HEIGHT + pad);
      const g = glyphs[i];
      for (let y = 0; y < FONT_HEIGHT; y++) for (let x = 0; x < 8; x++) if (glyphPixel(g, x, y)) ctx.fillRect(gx + x, gy + y, 1, 1);
    }
  }, [glyphs, color]);
  return <canvas ref={ref} className="pixel" style={{ width: `calc(${scale} * 145px)`, border: "1px solid var(--border)" }} />;
}

function TextRender({ glyphs, text, scale, color }: { glyphs: Glyph[]; text: string; scale: number; color: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    let total = 2;
    for (const ch of text) total += Math.max(glyphs[ch.charCodeAt(0) & 0xff].width || 6, 1) + 1;
    const W = Math.max(total, 8);
    const H = FONT_HEIGHT + 4;
    c.width = W;
    c.height = H;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#0d0b08";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = color;
    let pen = 2;
    for (const ch of text) {
      const g = glyphs[ch.charCodeAt(0) & 0xff];
      const w = Math.max(g.width || 6, 1);
      for (let y = 0; y < FONT_HEIGHT; y++) for (let x = 0; x < 8; x++) if (glyphPixel(g, x, y)) ctx.fillRect(pen + x, 2 + y, 1, 1);
      pen += w + 1;
    }
  }, [glyphs, text, color]);
  return <canvas ref={ref} className="pixel" style={{ height: `calc(${scale} * ${FONT_HEIGHT + 4}px)`, border: "1px solid var(--border)", maxWidth: "100%" }} />;
}

export function FontViewer() {
  const [glyphs, setGlyphs] = useState<Glyph[] | null>(null);
  const [name, setName] = useState("");
  const [scale, setScale] = useState(3);
  const [color, setColor] = useState("#e8a838");
  const [text, setText] = useState("The spice must flow.");

  return (
    <div className="col">
      <LoadBar accept=".BIN,.bin" sampleName="DNCHAR.BIN" hint="Load DNCHAR.BIN (or DNCHAR2.BIN) — the game's bitmap font." onLoad={(n, b) => { try { setGlyphs(decodeDnchar(b)); setName(n); } catch (e) { alert("Not a font: " + e); } }} />

      {glyphs && (
        <Panel
          title={`${name} — 256 glyphs (8×9)`}
          right={
            <div className="row small">
              <label className="muted">scale</label>
              <input type="range" min={1} max={6} value={scale} onChange={(e) => setScale(+e.target.value)} />
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)} title="ink color" />
            </div>
          }
        >
          <div className="col">
            <input className="mono" value={text} onChange={(e) => setText(e.target.value)} placeholder="type to preview the font…" />
            <TextRender glyphs={glyphs} text={text} scale={scale} color={color} />
            <div className="small muted" style={{ marginTop: 6 }}>Full glyph atlas (proportional widths from the font's width table):</div>
            <Atlas glyphs={glyphs} scale={Math.min(scale, 4)} color={color} />
          </div>
        </Panel>
      )}
    </div>
  );
}
