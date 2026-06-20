import { useEffect, useMemo, useRef, useState } from "react";
import { hsqCompress } from "../codecs/compression";
import {
  decodeSprite,
  detectAnimations,
  encodeSpriteFile,
  loadSpriteFile,
  quantizeToSprite,
  spriteBody,
  spriteToRGBA,
  type EncSprite,
  type RGB,
  type Sprite,
  type SpriteFile,
} from "../codecs/sprite";
import { detectCycleRanges, rotatePalette } from "../codecs/palette";
import { downloadBytes, hex, LoadBar, Panel, Tag } from "./shared";
import { useIncoming } from "./routing";

/** Draw an image file into a w×h RGBA buffer (scaled to fit). */
function imageFileToRGBA(file: File, w: number, h: number): Promise<Uint8ClampedArray> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = w;
      c.height = h;
      const ctx = c.getContext("2d");
      if (!ctx) return reject(new Error("no ctx"));
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      resolve(ctx.getImageData(0, 0, w, h).data);
      URL.revokeObjectURL(img.src);
    };
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

function SpriteCell(props: {
  name: string;
  idx: number;
  sprite: Sprite;
  palette: Map<number, RGB>;
  scale: number;
  opaque: boolean;
  replaced: boolean;
  onReplace: (idx: number, file: File) => void;
}) {
  const { sprite, palette, scale, opaque } = props;
  const ref = useRef<HTMLCanvasElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
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
        #{props.idx} · {w}×{h} · pal {hex(sprite.paletteOffset)}
        {props.replaced && " "}
        {props.replaced && <Tag color="var(--amber)">edited</Tag>}
      </div>
      {w > 0 && h > 0 && (
        <div className="row small" style={{ gap: 4 }}>
          <button className="btn small" onClick={download}>PNG</button>
          <button className="btn small" onClick={() => fileRef.current?.click()}>replace…</button>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => e.target.files?.[0] && props.onReplace(props.idx, e.target.files[0])} />
        </div>
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
  const spritesRef = useRef<Sprite[]>([]);
  const replacedRef = useRef<Set<number>>(new Set());
  const [, setVer] = useState(0);
  const bump = () => setVer((v) => v + 1);

  const load = (n: string, bytes: Uint8Array) => {
    setName(n.replace(/\.[^.]+$/, ""));
    setError("");
    try {
      const sf = loadSpriteFile(bytes);
      const arr: Sprite[] = [];
      for (let i = 0; i < sf.count; i++) {
        try {
          arr.push(decodeSprite(sf.data, i));
        } catch {
          arr.push({ width: 0, height: 0, paletteOffset: 0, compressed: false, pixels: new Uint8Array(0) });
        }
      }
      spritesRef.current = arr;
      replacedRef.current = new Set();
      setFile(sf);
    } catch (e) {
      setFile(null);
      setError(`Not a decodable sprite file: ${String(e)}`);
    }
  };

  const onReplace = async (idx: number, f: File) => {
    if (!file) return;
    const spr = spritesRef.current[idx];
    if (spr.width === 0 || spr.height === 0) return;
    try {
      const rgba = await imageFileToRGBA(f, spr.width, spr.height);
      const pixels = quantizeToSprite(rgba, spr.width, spr.height, file.palette, spr.paletteOffset);
      spritesRef.current[idx] = { ...spr, pixels };
      replacedRef.current.add(idx);
      bump();
    } catch (e) {
      alert("Could not load image: " + e);
    }
  };

  const exportHsq = () => {
    if (!file) return;
    // Unedited sprites pass through verbatim (byte-identical); only replaced
    // sprites are re-encoded — so an untouched export equals the original.
    const sprites: EncSprite[] = spritesRef.current.map((s, i) =>
      replacedRef.current.has(i)
        ? { width: s.width, height: s.height, paletteOffset: s.paletteOffset, pixels: s.pixels }
        : { width: s.width, height: s.height, paletteOffset: s.paletteOffset, pixels: s.pixels, raw: spriteBody(file, i) },
    );
    const decompressed = encodeSpriteFile({ paletteBytes: file.paletteBytes, hasExtra: file.hasExtra, sprites });
    downloadBytes(`${name}.HSQ`, hsqCompress(decompressed));
  };

  useIncoming("sprites", load);

  // Colour cycling: rotate contiguous palette ramps to preview shimmer effects.
  const [cycle, setCycle] = useState(false);
  const [cycleSpeed, setCycleSpeed] = useState(8); // steps/sec
  const [phase, setPhase] = useState(0);
  const [disabledRanges, setDisabledRanges] = useState<Set<number>>(new Set());
  const ranges = useMemo(() => (file ? detectCycleRanges(file.palette) : []), [file]);
  useEffect(() => {
    setDisabledRanges(new Set());
    setPhase(0);
  }, [file]);
  useEffect(() => {
    if (!cycle || ranges.length === 0) return;
    const id = setInterval(() => setPhase((p) => p + 1), Math.max(40, 1000 / Math.max(1, cycleSpeed)));
    return () => clearInterval(id);
  }, [cycle, cycleSpeed, ranges.length]);
  const activeRanges = useMemo(() => ranges.filter((_, i) => !disabledRanges.has(i)), [ranges, disabledRanges]);
  const livePalette = useMemo(
    () => (file && cycle ? rotatePalette(file.palette, activeRanges, phase) : file?.palette ?? new Map()),
    [file, cycle, activeRanges, phase],
  );

  const paletteEntries = useMemo(() => [...livePalette.entries()].sort((a, b) => a[0] - b[0]), [livePalette]);
  const inRange = useMemo(() => {
    const s = new Set<number>();
    for (const r of activeRanges) for (let i = r.start; i <= r.end; i++) s.add(i);
    return s;
  }, [activeRanges]);

  // Candidate animation sequences (consecutive same-size frames).
  const anims = useMemo(() => (file ? detectAnimations(file) : []), [file]);
  const [selAnim, setSelAnim] = useState(0);
  const [animFps, setAnimFps] = useState(8);
  const [animPlaying, setAnimPlaying] = useState(false);
  const [animFrame, setAnimFrame] = useState(0);
  const animRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    setSelAnim(0);
    setAnimFrame(0);
    setAnimPlaying(false);
  }, [file]);
  useEffect(() => {
    const a = anims[selAnim];
    if (!animPlaying || !a) return;
    const id = setInterval(() => setAnimFrame((f) => (f + 1) % a.count), Math.max(30, 1000 / Math.max(1, animFps)));
    return () => clearInterval(id);
  }, [animPlaying, selAnim, animFps, anims]);
  useEffect(() => {
    const a = anims[selAnim];
    const c = animRef.current;
    if (!a || !c || !file) return;
    const s = spritesRef.current[a.start + (animFrame % a.count)];
    if (!s || s.width === 0) return;
    c.width = a.width;
    c.height = a.height;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(a.width, a.height);
    img.data.set(spriteToRGBA(s, livePalette, opaque));
    ctx.putImageData(img, 0, 0);
  }, [anims, selAnim, animFrame, livePalette, opaque, file]);
  const editedCount = replacedRef.current.size;

  return (
    <div className="col">
      <LoadBar accept=".HSQ,.hsq" sampleName="CHAN.HSQ" hint="Load a sprite HSQ (e.g. CHAN, PERS, BARO, MAP2). Replace frames with PNGs and re-export." onLoad={load} />
      {error && <div className="warn small">{error}</div>}

      {file && (
        <Panel
          title={`${name} — ${file.count} sprites, ${file.palette.size} palette colors`}
          right={
            <div className="row small">
              <label className="muted">scale</label>
              <input type="range" min={1} max={8} value={scale} onChange={(e) => setScale(+e.target.value)} />
              <label className="muted">
                <input type="checkbox" checked={opaque} onChange={(e) => setOpaque(e.target.checked)} /> opaque
              </label>
              {ranges.length > 0 && (
                <label className="muted" title={`${ranges.length} cyclable colour ramp(s) detected`}>
                  <input type="checkbox" checked={cycle} onChange={(e) => setCycle(e.target.checked)} /> ✨ cycle
                </label>
              )}
              {cycle && ranges.length > 0 && (
                <input type="range" min={1} max={30} value={cycleSpeed} title="cycle speed" onChange={(e) => setCycleSpeed(+e.target.value)} />
              )}
              {editedCount > 0 && <Tag color="var(--amber)">{editedCount} edited</Tag>}
              <button className="btn primary" onClick={exportHsq}>⤓ Export .HSQ</button>
            </div>
          }
        >
          {paletteEntries.length > 0 && (
            <div className="row" style={{ gap: 2, marginBottom: 10 }}>
              {paletteEntries.map(([idx, [r, g, b]]) => (
                <span
                  key={idx}
                  className="swatch"
                  title={`${idx}: ${r},${g},${b}${inRange.has(idx) ? " (cycling)" : ""}`}
                  style={{ background: `rgb(${r},${g},${b})`, outline: cycle && inRange.has(idx) ? "1px solid var(--amber)" : undefined }}
                />
              ))}
            </div>
          )}
          {ranges.length > 0 && (
            <div className="row small muted" style={{ gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
              <span>Colour-cycle ramps:</span>
              {ranges.map((r, i) => (
                <label key={i} style={{ cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={!disabledRanges.has(i)}
                    onChange={(e) =>
                      setDisabledRanges((prev) => {
                        const n = new Set(prev);
                        if (e.target.checked) n.delete(i);
                        else n.add(i);
                        return n;
                      })
                    }
                  />{" "}
                  {hex(r.start)}–{hex(r.end)}
                </label>
              ))}
              <span className="muted">(heuristic ranges; exact engine ranges live in the EXE)</span>
            </div>
          )}
          {anims.length > 0 && (
            <div className="row small" style={{ gap: 10, marginBottom: 10, alignItems: "center", flexWrap: "wrap" }}>
              <b>Animations:</b>
              <select value={selAnim} onChange={(e) => { setSelAnim(+e.target.value); setAnimFrame(0); }}>
                {anims.map((a, i) => (
                  <option key={i} value={i}>#{i}: sprites {a.start}–{a.start + a.count - 1} ({a.count}f, {a.width}×{a.height})</option>
                ))}
              </select>
              <button className="btn small" onClick={() => setAnimPlaying((p) => !p)}>{animPlaying ? "■ stop" : "▶ play"}</button>
              <label className="muted">fps</label>
              <input type="range" min={1} max={24} value={animFps} onChange={(e) => setAnimFps(+e.target.value)} />
              {anims[selAnim] && <span className="muted">frame {(animFrame % anims[selAnim].count) + 1}/{anims[selAnim].count}</span>}
              <canvas ref={animRef} className="pixel" style={{ width: (anims[selAnim]?.width ?? 0) * 2, height: (anims[selAnim]?.height ?? 0) * 2, imageRendering: "pixelated", border: "1px solid var(--border)", background: "#101018" }} />
              <span className="muted">(heuristic frame groups; exact sequences/timing live in the EXE)</span>
            </div>
          )}
          <div className="small muted" style={{ marginBottom: 8 }}>
            Graphics mod loop: <b>replace…</b> a frame with a PNG (auto-mapped to that sprite's 16-colour window), then{" "}
            <b>Export .HSQ</b> and put it back via the <b>Archive</b> tab.
          </div>
          <div className="row" style={{ alignItems: "flex-start" }}>
            {spritesRef.current.map((s, i) => (
              <SpriteCell key={i} name={name} idx={i} sprite={s} palette={livePalette} scale={scale} opaque={opaque} replaced={replacedRef.current.has(i)} onReplace={onReplace} />
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
