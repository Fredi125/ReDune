import { useEffect, useRef, useState } from "react";
import { decodeMap, MAP_WIDTHS, renderMapRGBA } from "../codecs/map";
import { LoadBar, Panel } from "./shared";

export function MapViewer() {
  const [name, setName] = useState("");
  const [data, setData] = useState<Uint8Array | null>(null);
  const [error, setError] = useState("");
  const [width, setWidth] = useState(0); // 0 = auto
  const [scale, setScale] = useState(2);
  const ref = useRef<HTMLCanvasElement>(null);

  const load = (n: string, bytes: Uint8Array) => {
    setError("");
    try {
      setData(decodeMap(bytes));
      setName(n);
    } catch (e) {
      setData(null);
      setError(String(e));
    }
  };

  useEffect(() => {
    const c = ref.current;
    if (!c || !data) return;
    const img = renderMapRGBA(data, width || undefined);
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const id = ctx.createImageData(img.width, img.height);
    id.data.set(img.rgba);
    ctx.putImageData(id, 0, 0);
  }, [data, width]);

  return (
    <div className="col">
      <LoadBar accept=".HSQ,.hsq" sampleName="MAP.HSQ" hint="Load MAP.HSQ — the world terrain data." onLoad={load} />
      {error && <div className="warn small">Couldn't decode map: {error}</div>}

      {data && (
        <Panel
          title={`${name} — ${data.length.toLocaleString()} terrain bytes`}
          right={
            <div className="row small">
              <label className="muted">width</label>
              <select value={width} onChange={(e) => setWidth(+e.target.value)}>
                <option value={0}>auto</option>
                {MAP_WIDTHS.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
              <label className="muted">scale</label>
              <input type="range" min={1} max={4} value={scale} onChange={(e) => setScale(+e.target.value)} />
            </div>
          }
        >
          <div style={{ overflow: "auto", maxHeight: 520 }}>
            <canvas ref={ref} className="pixel" style={{ width: `calc(${scale} * 320px)`, imageRendering: "pixelated" }} />
          </div>
          <div className="small muted" style={{ marginTop: 8 }}>
            Heatmap preview (low = blue/sand → high = red/white rock). The game's true globe projection (via TABLAT) isn't
            fully reversed yet; this lays terrain bytes out row-major to reveal the world's structure.
          </div>
        </Panel>
      )}
    </div>
  );
}
