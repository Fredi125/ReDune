import { useEffect, useMemo, useRef, useState } from "react";
import { decodeSprite, loadSpriteFile, spriteToRGBA, type RGB, type Sprite, type SpriteFile } from "../codecs/sprite";
import { hex, LoadBar, Panel } from "./shared";

function SpriteCell(props: { name: string; idx: number; sprite: Sprite; palette: Map<number, RGB>; scale: number; opaque: boolean }) {
  const { sprite, palette, scale, opaque } = props;
  const ref = useRef<HTMLCanvasElement>(null);
  const { width: w, height: h } = sprite;

  useEffect(() => {
    const c = ref.current;
    if (!c || w === 0 || h === 0) return;
    c.width = w;
    c.height = h;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(w, h);
    img.data.set(spriteToRGBA(sprite, palette, opaque));
    ctx.putImageData(img, 0, 0);
  }, [sprite, palette, opaque, w, h]);

  const download = () => {
    ref.current?.toBlob((b) => {
      if (!b) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `${props.name}_${String(props.idx).padStart(3, "0")}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    });
  };

  return (
    <div className="sprite-cell">
      {w === 0 || h === 0 ? (
        <div className="muted small" style={{ padding: 12 }}>(empty)</div>
      ) : (
        <canvas ref={ref} className="pixel" style={{ width: w * scale, height: h * scale, maxWidth: 320 }} />
      )}
      <div className="small muted">
        #{props.idx} · {w}×{h} · pal {hex(sprite.paletteOffset)} · {sprite.compressed ? "RLE" : "raw"}
      </div>
      {w > 0 && h > 0 && (
        <button className="btn small" onClick={download}>
          PNG
        </button>
      )}
    </div>
  );
}

export function SpriteViewer() {
  const [name, setName] = useState("");
  const [file, setFile] = useState<SpriteFile | null>(null);
  const [error, setError] = useState("");
  const [scale, setScale] = useState(3);
  const [opaque, setOpaque] = useState(false);

  const load = (n: string, bytes: Uint8Array) => {
    setName(n.replace(/\.[^.]+$/, ""));
    setError("");
    try {
      setFile(loadSpriteFile(bytes));
    } catch (e) {
      setFile(null);
      setError(`Not a decodable sprite file: ${String(e)}`);
    }
  };

  const sprites = useMemo(() => {
    if (!file) return [];
    const out: Sprite[] = [];
    for (let i = 0; i < file.count; i++) {
      try {
        out.push(decodeSprite(file.data, i));
      } catch {
        out.push({ width: 0, height: 0, paletteOffset: 0, compressed: false, pixels: new Uint8Array(0) });
      }
    }
    return out;
  }, [file]);

  const paletteEntries = useMemo(() => (file ? [...file.palette.entries()].sort((a, b) => a[0] - b[0]) : []), [file]);

  return (
    <div className="col">
      <LoadBar
        accept=".HSQ,.hsq"
        sampleName="CHAN.HSQ"
        hint="Load a sprite HSQ (e.g. CHAN.HSQ, PERS.HSQ, MAP2.HSQ, BACK.HSQ)."
        onLoad={load}
      />
      {error && <div className="warn small">{error}</div>}

      {file && (
        <>
          <Panel
            title={`${name} — ${file.count} sprites, ${file.palette.size} palette colors`}
            right={
              <div className="row small">
                <label className="muted">scale</label>
                <input type="range" min={1} max={8} value={scale} onChange={(e) => setScale(+e.target.value)} />
                <label className="muted">
                  <input type="checkbox" checked={opaque} onChange={(e) => setOpaque(e.target.checked)} /> opaque
                </label>
              </div>
            }
          >
            {paletteEntries.length > 0 && (
              <div className="row" style={{ gap: 2, marginBottom: 10 }}>
                {paletteEntries.map(([idx, [r, g, b]]) => (
                  <span key={idx} className="swatch" title={`${idx}: ${r},${g},${b}`} style={{ background: `rgb(${r},${g},${b})` }} />
                ))}
              </div>
            )}
            <div className="row" style={{ alignItems: "flex-start" }}>
              {sprites.map((s, i) => (
                <SpriteCell key={i} name={name} idx={i} sprite={s} palette={file.palette} scale={scale} opaque={opaque} />
              ))}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
