import { useEffect, useRef, useState } from "react";
import { decodeDnchar, encodeDnchar, FONT_HEIGHT, glyphPixel, setGlyphPixel, type Glyph } from "../codecs/font";
import { downloadBytes, LoadBar, NumberField, Panel } from "./shared";

function Atlas({ glyphs, scale, color, sel, onPick, rev }: { glyphs: Glyph[]; scale: number; color: string; sel: number; onPick: (i: number) => void; rev: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const cols = 16;
  const rows = 16;
  const cw = 8;
  const pad = 1;
  const W = cols * (cw + pad) + pad;
  const H = rows * (FONT_HEIGHT + pad) + pad;
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    c.width = W;
    c.height = H;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#0d0b08";
    ctx.fillRect(0, 0, W, H);
    for (let i = 0; i < 256; i++) {
      const gx = pad + (i % cols) * (cw + pad);
      const gy = pad + Math.floor(i / cols) * (FONT_HEIGHT + pad);
      if (i === sel) {
        ctx.fillStyle = "#e8a83833";
        ctx.fillRect(gx, gy, cw, FONT_HEIGHT);
      }
      ctx.fillStyle = color;
      const g = glyphs[i];
      if (g) for (let y = 0; y < FONT_HEIGHT; y++) for (let x = 0; x < 8; x++) if (glyphPixel(g, x, y)) ctx.fillRect(gx + x, gy + y, 1, 1);
    }
  }, [glyphs, color, sel, rev, W, H]);
  return (
    <canvas
      ref={ref}
      className="pixel"
      style={{ width: `calc(${scale} * ${W}px)`, border: "1px solid var(--border)", cursor: "pointer" }}
      onClick={(e) => {
        const c = ref.current;
        if (!c) return;
        const r = c.getBoundingClientRect();
        const px = ((e.clientX - r.left) / r.width) * W;
        const py = ((e.clientY - r.top) / r.height) * H;
        const col = Math.floor((px - pad) / (cw + pad));
        const row = Math.floor((py - pad) / (FONT_HEIGHT + pad));
        if (col >= 0 && col < cols && row >= 0 && row < rows) onPick(row * cols + col);
      }}
    />
  );
}

function TextRender({ glyphs, text, scale, color, rev }: { glyphs: Glyph[]; text: string; scale: number; color: string; rev: number }) {
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
  }, [glyphs, text, color, rev]);
  return <canvas ref={ref} className="pixel" style={{ height: `calc(${scale} * ${FONT_HEIGHT + 4}px)`, border: "1px solid var(--border)", maxWidth: "100%" }} />;
}

export function FontViewer() {
  const glyphsRef = useRef<Glyph[] | null>(null);
  const rawRef = useRef<Uint8Array | null>(null);
  const [name, setName] = useState("");
  const [, setVer] = useState(0);
  const rev = useRef(0);
  const bump = () => {
    rev.current++;
    setVer(rev.current);
  };
  const [scale, setScale] = useState(3);
  const [color, setColor] = useState("#e8a838");
  const [text, setText] = useState("The spice must flow.");
  const [sel, setSel] = useState(65);

  const glyphs = glyphsRef.current;

  return (
    <div className="col">
      <LoadBar
        accept=".BIN,.bin"
        sampleName="DNCHAR.BIN"
        hint="Load DNCHAR.BIN (or DNCHAR2.BIN) — the bitmap font. Click a glyph to edit its pixels, then export."
        onLoad={(n, b) => {
          try {
            glyphsRef.current = decodeDnchar(b);
            rawRef.current = b;
            setName(n);
            bump();
          } catch (e) {
            alert("Not a font: " + e);
          }
        }}
      />

      {glyphs && (
        <Panel
          title={`${name} — 256 glyphs (8×9)`}
          right={
            <div className="row small">
              <label className="muted">scale</label>
              <input type="range" min={1} max={6} value={scale} onChange={(e) => setScale(+e.target.value)} />
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)} title="ink color" />
              <button className="btn primary" onClick={() => downloadBytes((name || "DNCHAR") + ".BIN", encodeDnchar(glyphs, rawRef.current ?? undefined))}>⤓ Export .BIN</button>
            </div>
          }
        >
          <div className="row" style={{ alignItems: "flex-start", gap: 16 }}>
            <div className="col">
              <input className="mono" value={text} onChange={(e) => setText(e.target.value)} placeholder="type to preview…" />
              <TextRender glyphs={glyphs} text={text} scale={scale} color={color} rev={rev.current} />
              <div className="small muted" style={{ marginTop: 6 }}>Click a glyph in the atlas to edit it:</div>
              <Atlas glyphs={glyphs} scale={Math.min(scale, 4)} color={color} sel={sel} onPick={setSel} rev={rev.current} />
            </div>

            {/* glyph editor */}
            <Panel title={`Glyph ${sel} (${sel >= 32 && sel < 127 ? `'${String.fromCharCode(sel)}'` : "0x" + sel.toString(16).toUpperCase()})`} accent="var(--blue)">
              <div className="col">
                <NumberField label="advance width" value={glyphs[sel].width} max={255} onChange={(v) => { glyphs[sel].width = v; bump(); }} style={{ width: 120 }} />
                <div style={{ display: "grid", gridTemplateColumns: "repeat(8, 18px)", gap: 1, background: "var(--border)", padding: 1, width: "fit-content" }}>
                  {Array.from({ length: FONT_HEIGHT * 8 }, (_, k) => {
                    const x = k % 8;
                    const y = Math.floor(k / 8);
                    const on = glyphPixel(glyphs[sel], x, y);
                    return (
                      <div
                        key={k}
                        onClick={() => { setGlyphPixel(glyphs[sel], x, y, !on); bump(); }}
                        style={{ width: 18, height: 18, background: on ? color : "#0d0b08", cursor: "pointer" }}
                        title={`(${x},${y})`}
                      />
                    );
                  })}
                </div>
                <div className="small muted">8×9 pixels · MSB = leftmost. Edits update the preview &amp; atlas live; Export writes a byte-identical .BIN (with your edits).</div>
              </div>
            </Panel>
          </div>
        </Panel>
      )}
    </div>
  );
}
