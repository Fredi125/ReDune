import { useEffect, useRef, useState } from "react";
import { decodeMap, heatmapColor, MAP_WIDTHS, renderMapRGBA } from "../codecs/map";
import { loadGlobe, type GlobeScanline } from "../codecs/globdata";
import { LoadBar, Panel } from "./shared";

const GLOBE_R = 95;
const GLOBE_SZ = 2 * GLOBE_R + 10;

export function MapViewer() {
  const [mode, setMode] = useState<"flat" | "globe">("flat");
  const [mapData, setMapData] = useState<Uint8Array | null>(null);
  const [mapName, setMapName] = useState("");
  const [globe, setGlobe] = useState<GlobeScanline[] | null>(null);
  const [globeName, setGlobeName] = useState("");
  const [error, setError] = useState("");
  const [width, setWidth] = useState(0);
  const [scale, setScale] = useState(2);
  const [rot, setRot] = useState(0);
  const [spin, setSpin] = useState(false);
  const flatRef = useRef<HTMLCanvasElement>(null);
  const globeRef = useRef<HTMLCanvasElement>(null);

  const loadMap = (n: string, bytes: Uint8Array) => {
    setError("");
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

  // flat heatmap
  useEffect(() => {
    if (mode !== "flat") return;
    const c = flatRef.current;
    if (!c || !mapData) return;
    const img = renderMapRGBA(mapData, width || undefined);
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const id = ctx.createImageData(img.width, img.height);
    id.data.set(img.rgba);
    ctx.putImageData(id, 0, 0);
  }, [mode, mapData, width]);

  // globe sphere (experimental projection from the GLOBDATA latitude blocks)
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
      const halfW = R * cosLat;
      for (let px = 0; px < GLOBE_SZ; px++) {
        const dx = px - cx;
        if (Math.abs(dx) > halfW || halfW < 1) continue;
        const p = (dx / halfW + 1) / 2; // 0..1 across visible arc
        const rampIdx = Math.min(blk.ramp.length - 1, Math.max(0, Math.round(p * (blk.ramp.length - 1))));
        const lon = blk.ramp[rampIdx];
        const tIdx = (((lon >> 1) + rot) % tlen + tlen) % tlen;
        const [r, g, bl] = heatmapColor(blk.terrain[tIdx]);
        // simple sphere shading toward the limb
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
  }, [mode, globe, rot]);

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
              <canvas ref={flatRef} className="pixel" style={{ width: `calc(${scale} * 320px)`, imageRendering: "pixelated" }} />
            </div>
          ) : (
            <canvas ref={globeRef} className="pixel" style={{ width: GLOBE_SZ * 2, height: GLOBE_SZ * 2, imageRendering: "pixelated" }} />
          )}
          <div className="small muted" style={{ marginTop: 8 }}>
            {mode === "flat"
              ? "Heatmap preview (low = blue/sand → high = red/white rock)."
              : "Experimental globe: each latitude's terrain bytes from GLOBDATA, projected onto a sphere via the longitude ramps (validated parse; exact pixel projection from the ASM is still pending)."}
          </div>
        </Panel>
      )}
    </div>
  );
}
