import { useEffect, useRef, useState } from "react";
import { decodeMap, detectMapWidth, heatmapColor, MAP_WIDTHS, planetColor, renderMapRGBA, sandColor } from "../codecs/map";
import { hsqCompress } from "../codecs/compression";
import { loadGlobe, type GlobeScanline } from "../codecs/globdata";
import { parseTablat, tablatScaleCurve } from "../codecs/tablat";
import { downloadBytes, LoadBar, Panel } from "./shared";
import { useTint } from "./tint";
import { useIncoming } from "./routing";

const GLOBE_R = 95;
const GLOBE_SZ = 2 * GLOBE_R + 10;

export function MapViewer() {
  const tint = useTint();
  const [mode, setMode] = useState<"flat" | "globe">("flat");
  const [mapData, setMapData] = useState<Uint8Array | null>(null);
  const [mapName, setMapName] = useState("");
  const [globe, setGlobe] = useState<GlobeScanline[] | null>(null);
  const [globeName, setGlobeName] = useState("");
  const [scaleCurve, setScaleCurve] = useState<number[] | null>(null);
  const [tablatName, setTablatName] = useState("");
  const [error, setError] = useState("");
  const [width, setWidth] = useState(0);
  const [scale, setScale] = useState(2);
  const [rot, setRot] = useState(0);
  const [spin, setSpin] = useState(false);
  const [editing, setEditing] = useState(false);
  const [heatmap, setHeatmap] = useState(false); // false = Arrakis sand palette (default), true = analytic heatmap
  const [brush, setBrush] = useState(0xc0);
  const [rev, setRev] = useState(0);
  const [dirty, setDirty] = useState(false);
  const painting = useRef(false);
  const flatRef = useRef<HTMLCanvasElement>(null);
  const globeRef = useRef<HTMLCanvasElement>(null);

  const paintAt = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const c = flatRef.current;
    if (!c || !mapData) return;
    const w = width || detectMapWidth(mapData.length);
    const h = Math.floor(mapData.length / w);
    const r = c.getBoundingClientRect();
    const px = Math.floor(((e.clientX - r.left) / r.width) * w);
    const py = Math.floor(((e.clientY - r.top) / r.height) * h);
    if (px < 0 || py < 0 || px >= w || py >= h) return;
    const i = py * w + px;
    if (mapData[i] === brush) return;
    mapData[i] = brush;
    setDirty(true);
    setRev((v) => v + 1);
  };

  const exportMap = () => {
    if (!mapData) return;
    downloadBytes(mapName || "MAP.HSQ", hsqCompress(mapData));
  };

  const loadMap = (n: string, bytes: Uint8Array) => {
    setError("");
    setDirty(false);
    setEditing(false);
    try {
      setMapData(decodeMap(bytes));
      setMapName(n);
      setMode("flat");
    } catch (e) {
      setError(String(e));
    }
  };
  const loadGlobeFile = (n: string, bytes: Uint8Array) => {
    setError("");
    try {
      setGlobe(loadGlobe(bytes));
      setGlobeName(n);
      setMode("globe");
    } catch (e) {
      setError(String(e));
    }
  };
  const loadTablat = (n: string, bytes: Uint8Array) => {
    setError("");
    try {
      const curve = tablatScaleCurve(parseTablat(bytes));
      setScaleCurve(curve.some((s) => s > 0) ? curve : null);
      setTablatName(n);
    } catch (e) {
      setError(String(e));
    }
  };

  // Auto-detect routes MAP / GLOBDATA / TABLAT here; pick the right loader by name.
  useIncoming("map", (n, b) => {
    const u = n.toUpperCase();
    if (u.includes("GLOBDATA")) loadGlobeFile(n, b);
    else if (u.includes("TABLAT")) loadTablat(n, b);
    else loadMap(n, b);
  });

  // flat heatmap
  useEffect(() => {
    if (mode !== "flat") return;
    const c = flatRef.current;
    if (!c || !mapData) return;
    const img = renderMapRGBA(mapData, width || undefined, heatmap ? heatmapColor : sandColor);
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const id = ctx.createImageData(img.width, img.height);
    id.data.set(img.rgba);
    ctx.putImageData(id, 0, 0);
  }, [mode, mapData, width, rev, heatmap]);

  // globe sphere: the GLOBDATA longitude ramps + TABLAT foreshortening give the
  // geometry; when MAP.HSQ is loaded we wrap the *real* world terrain onto it
  // (desert palette), otherwise we fall back to the GLOBDATA latitude bytes.
  // Ground truth (DN386 sphere-fill @0x1B8C): disc centred col 160 / rows 79–80,
  // filled symmetrically outward, 200-byte source pitch, half-width from TABLAT;
  // planet colours come from palette bank 0x10–0x1F (planetColor) — NOT the
  // 0x80–0xBF cycle band. Rotation is caller-driven, so `rot` stands in for it.
  useEffect(() => {
    if (mode !== "globe") return;
    const c = globeRef.current;
    if (!c || !globe || globe.length === 0) return;
    c.width = GLOBE_SZ;
    c.height = GLOBE_SZ;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const out = new Uint8ClampedArray(GLOBE_SZ * GLOBE_SZ * 4);
    const cx = GLOBE_SZ / 2;
    const cy = GLOBE_SZ / 2;
    const R = GLOBE_R;
    const nLat = globe.length;
    const maxScale = scaleCurve ? Math.max(...scaleCurve) : 0;
    const rampMaxAll = Math.max(1, ...globe.map((b) => b.rampMax));
    // Real-terrain source (optional): wrap MAP.HSQ around the sphere.
    const mapW = mapData ? detectMapWidth(mapData.length) : 0;
    const mapH = mapData ? Math.floor(mapData.length / mapW) : 0;
    const rotCols = mapW ? Math.round((rot / 100) * mapW) : 0;
    for (let py = 0; py < GLOBE_SZ; py++) {
      const dy = py - cy;
      if (Math.abs(dy) > R) continue;
      const sinLat = dy / R;
      const cosLat = Math.sqrt(Math.max(0, 1 - sinLat * sinLat));
      const latNorm = Math.asin(Math.max(-1, Math.min(1, sinLat))) / (Math.PI / 2); // -1..1
      const b = Math.min(nLat - 1, Math.max(0, Math.round(Math.abs(latNorm) * (nLat - 1))));
      const blk = globe[b];
      const tlen = blk.terrain.length;
      if (tlen === 0) continue;
      const mapRow = mapData ? Math.min(mapH - 1, Math.max(0, Math.round((0.5 - latNorm * 0.5) * (mapH - 1)))) : 0;
      // Foreshortening width: from the real TABLAT scale curve if loaded, else geometric cos.
      let halfW = R * cosLat;
      if (scaleCurve && maxScale > 0) {
        const li = Math.min(scaleCurve.length - 1, Math.max(0, Math.round(Math.abs(latNorm) * (scaleCurve.length - 1))));
        halfW = (scaleCurve[li] / maxScale) * R;
      }
      for (let px = 0; px < GLOBE_SZ; px++) {
        const dx = px - cx;
        if (Math.abs(dx) > halfW || halfW < 1) continue;
        const p = (dx / halfW + 1) / 2; // 0..1 across visible arc
        const rampIdx = Math.min(blk.ramp.length - 1, Math.max(0, Math.round(p * (blk.ramp.length - 1))));
        const lon = blk.ramp[rampIdx];
        let val: number;
        if (mapData) {
          // longitude ramp → column within the visible hemisphere (mapW/2), spun by rot
          const col = (((Math.round((lon / rampMaxAll) * (mapW / 2)) + rotCols) % mapW) + mapW) % mapW;
          val = mapData[mapRow * mapW + col];
        } else {
          const tIdx = (((lon >> 1) + rot) % tlen + tlen) % tlen;
          val = blk.terrain[tIdx];
        }
        const [r, g, bl] = planetColor(val);
        // sphere shading toward the limb
        const shade = 0.55 + 0.45 * cosLat;
        const o = (py * GLOBE_SZ + px) * 4;
        out[o] = r * shade;
        out[o + 1] = g * shade;
        out[o + 2] = bl * shade;
        out[o + 3] = 255;
      }
    }
    const id = ctx.createImageData(GLOBE_SZ, GLOBE_SZ);
    id.data.set(out);
    ctx.putImageData(id, 0, 0);
  }, [mode, globe, rot, scaleCurve, mapData]);

  // auto-spin
  useEffect(() => {
    if (!spin || mode !== "globe") return;
    const id = setInterval(() => setRot((r) => r + 1), 80);
    return () => clearInterval(id);
  }, [spin, mode]);

  return (
    <div className="col">
      <LoadBar accept=".HSQ,.hsq" sampleName="MAP.HSQ" hint="Load MAP.HSQ — the world terrain (flat heatmap view)." onLoad={loadMap} />
      <LoadBar accept=".HSQ,.hsq" sampleName="GLOBDATA.HSQ" hint={globe ? `${globeName} loaded ✓ — globe view available.` : "Optional: load GLOBDATA.HSQ for the spinning globe view."} onLoad={loadGlobeFile} />
      <LoadBar accept=".BIN,.bin" sampleName="TABLAT.BIN" hint={scaleCurve ? `${tablatName} loaded ✓ — globe foreshortening from the real latitude table.` : "Optional: load TABLAT.BIN to drive the globe's latitude foreshortening from the game's table."} onLoad={loadTablat} />
      {error && <div className="warn small">Couldn't decode: {error}</div>}

      {(mapData || globe) && (
        <Panel
          title={mode === "flat" ? `${mapName || "MAP"} — terrain heatmap` : `${globeName || "GLOBDATA"} — globe`}
          right={
            <div className="row small">
              <button className={"btn" + (mode === "flat" ? " primary" : "")} disabled={!mapData} onClick={() => setMode("flat")}>flat</button>
              <button className={"btn" + (mode === "globe" ? " primary" : "")} disabled={!globe} onClick={() => setMode("globe")}>globe</button>
              {mode === "flat" && (
                <>
                  <label className="muted">width</label>
                  <select value={width} onChange={(e) => setWidth(+e.target.value)}>
                    <option value={0}>auto</option>
                    {MAP_WIDTHS.map((w) => (<option key={w} value={w}>{w}</option>))}
                  </select>
                  <label className="muted">scale</label>
                  <input type="range" min={1} max={4} value={scale} onChange={(e) => setScale(+e.target.value)} />
                  <label className="muted" title="Arrakis sand palette vs analytic terrain heatmap (low→high)"><input type="checkbox" checked={heatmap} onChange={(e) => setHeatmap(e.target.checked)} /> heatmap</label>
                  <label className="muted" title="Click/drag the map to paint terrain"><input type="checkbox" checked={editing} onChange={(e) => setEditing(e.target.checked)} /> ✎ edit</label>
                  {editing && (
                    <>
                      <span className="swatch" title={`brush 0x${brush.toString(16)}`} style={{ background: `rgb(${planetColor(brush).join(",")})`, width: 16, height: 16, display: "inline-block", border: "1px solid var(--border)" }} />
                      <input type="range" min={0} max={255} value={brush} title={`terrain 0x${brush.toString(16)}`} onChange={(e) => setBrush(+e.target.value)} />
                    </>
                  )}
                  {dirty && <button className="btn primary" onClick={exportMap}>⤓ Export .HSQ</button>}
                </>
              )}
              {mode === "globe" && (
                <>
                  <label className="muted">rotate</label>
                  <input type="range" min={0} max={99} value={rot % 100} onChange={(e) => setRot(+e.target.value)} />
                  <label className="muted"><input type="checkbox" checked={spin} onChange={(e) => setSpin(e.target.checked)} /> spin</label>
                </>
              )}
            </div>
          }
        >
          {mode === "flat" ? (
            <div style={{ overflow: "auto", maxHeight: 520 }}>
              <canvas
                ref={flatRef}
                className="pixel"
                style={{ width: `calc(${scale} * 320px)`, imageRendering: "pixelated", cursor: editing ? "crosshair" : "default", filter: tint.filter }}
                onMouseDown={editing ? (e) => { painting.current = true; paintAt(e); } : undefined}
                onMouseMove={editing ? (e) => { if (painting.current) paintAt(e); } : undefined}
                onMouseUp={() => { painting.current = false; }}
                onMouseLeave={() => { painting.current = false; }}
              />
            </div>
          ) : (
            <canvas ref={globeRef} className="pixel" style={{ width: GLOBE_SZ * 2, height: GLOBE_SZ * 2, imageRendering: "pixelated", filter: tint.filter }} />
          )}
          <div style={{ marginTop: 8 }}>{tint.controls}</div>
          <div className="small muted" style={{ marginTop: 8 }}>
            {mode === "flat"
              ? `${heatmap ? "Heatmap (low → high terrain: blue → red/white)." : "Arrakis sand palette (low → high: dark sand → pale rock). Toggle 'heatmap' for the analytic ramp."}${editing ? " ✎ Click/drag to paint the brush terrain value; ⤓ Export writes a valid MAP.HSQ that decodes to your edits." : " Toggle ✎ edit to paint terrain."}`
              : `Globe: ${mapData ? "the real MAP.HSQ terrain wrapped onto the sphere" : "GLOBDATA latitude bytes (load MAP.HSQ to wrap the real terrain)"} via the GLOBDATA longitude ramps${scaleCurve ? " + the real TABLAT foreshortening" : ""}, desert palette + limb shading. Geometry validated (TABLAT); exact ASM orientation/palette (sub_1BA75) still unpublished.`}
          </div>
        </Panel>
      )}
    </div>
  );
}
