import { useState } from "react";

/**
 * Reusable display-only colour-grade for rendered canvases (rooms, map, globe,
 * scene backgrounds). Returns a CSS `filter` string plus a small slider control
 * row. This adjusts the *displayed* image only — it never changes the decoded
 * data — which is handy because several palettes (globe bank RGB, palette-less
 * scene backgrounds) aren't byte-exact yet, so the user can tune them to taste.
 */
export function useTint() {
  const [hue, setHue] = useState(0); // -180..180 deg
  const [sat, setSat] = useState(100); // 0..200 %
  const [bri, setBri] = useState(100); // 50..150 %
  const active = hue !== 0 || sat !== 100 || bri !== 100;
  const filter = active ? `hue-rotate(${hue}deg) saturate(${sat}%) brightness(${bri}%)` : "none";
  const reset = () => {
    setHue(0);
    setSat(100);
    setBri(100);
  };
  const controls = (
    <div className="row small" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
      <span className="muted" title="Tint the rendered image (display only — does not change the decoded data)">🎨 tint</span>
      <label className="muted" style={{ display: "flex", gap: 4, alignItems: "center" }}>
        hue<input type="range" min={-180} max={180} value={hue} onChange={(e) => setHue(+e.target.value)} />
      </label>
      <label className="muted" style={{ display: "flex", gap: 4, alignItems: "center" }}>
        sat<input type="range" min={0} max={200} value={sat} onChange={(e) => setSat(+e.target.value)} />
      </label>
      <label className="muted" style={{ display: "flex", gap: 4, alignItems: "center" }}>
        bright<input type="range" min={50} max={150} value={bri} onChange={(e) => setBri(+e.target.value)} />
      </label>
      {active && (
        <button className="btn small" onClick={reset}>
          reset
        </button>
      )}
    </div>
  );
  return { filter, controls, active };
}
