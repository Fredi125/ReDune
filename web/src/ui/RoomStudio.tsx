import { useEffect, useRef, useState } from "react";
import { encodeSal, loadSal, sectionCounts, type SalFile, type SalSection } from "../codecs/sal";
import { decodeSprite, loadSpriteFile, spriteToRGBA, type RGB, type SpriteFile } from "../codecs/sprite";
import { recommendedDecoration } from "../codecs/constants";
import { downloadBytes, hex, LoadBar, NumberField, Panel, Tag } from "./shared";

/** Pre-render every sprite of the decoration sheet to its own canvas (alpha-keyed). */
function buildSpriteCanvases(sf: SpriteFile): (HTMLCanvasElement | null)[] {
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

function RoomCanvas(props: {
  section: SalSection;
  sprites: (HTMLCanvasElement | null)[] | null;
  palette: Map<number, RGB> | null;
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
        const pts: [number, number][] = [[cmd.initX, cmd.initY], ...cmd.verticesPass1];
        if (pts.length > 1) {
          ctx.beginPath();
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
          ctx.closePath();
          const rgb = palRgb(cmd.polySubtype, `${(cmd.polySubtype * 9) % 256},${(cmd.polySubtype * 5) % 256},150`);
          ctx.fillStyle = `rgba(${rgb},0.30)`;
          ctx.fill();
          ctx.strokeStyle = `rgba(${rgb},0.9)`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      } else if (cmd.type === "sprite" && props.show.sprites && props.sprites) {
        const sc = props.sprites[cmd.spriteIndex];
        if (sc) ctx.drawImage(sc, cmd.x, cmd.y);
      }
    }
  }, [props.section, props.sprites, props.palette, props.show, props.bg, props.rev]);

  return (
    <canvas
      ref={ref}
      className="pixel"
      style={{ width: W * props.scale, height: H * props.scale, border: "1px solid var(--border)", background: props.bg }}
    />
  );
}

export function RoomStudio() {
  const [sal, setSal] = useState<SalFile | null>(null);
  const [salName, setSalName] = useState("");
  const [sel, setSel] = useState(0);
  const [, setRev] = useState(0);
  const rev = useRef(0);
  const bump = () => {
    rev.current++;
    setRev(rev.current);
  };

  const [decoName, setDecoName] = useState("");
  const [sprites, setSprites] = useState<(HTMLCanvasElement | null)[] | null>(null);
  const [palette, setPalette] = useState<Map<number, RGB> | null>(null);
  const [spriteCount, setSpriteCount] = useState(0);

  const [scale, setScale] = useState(2);
  const [show, setShow] = useState({ sprites: true, polys: true, rects: true });
  const [bg, setBg] = useState("#101018");

  const loadSalFile = (n: string, bytes: Uint8Array) => {
    try {
      const s = loadSal(bytes);
      setSal(s);
      setSalName(n);
      setSel(0);
      bump();
    } catch (e) {
      alert("Not a SAL room file: " + e);
    }
  };

  const loadDeco = (n: string, bytes: Uint8Array) => {
    try {
      const sf: SpriteFile = loadSpriteFile(bytes);
      setSprites(buildSpriteCanvases(sf));
      setPalette(sf.palette);
      setSpriteCount(sf.count);
      setDecoName(n);
      bump();
    } catch (e) {
      alert("Not a sprite sheet: " + e);
    }
  };

  const section = sal && sel < sal.sections.length ? sal.sections[sel] : null;
  const tip = salName ? recommendedDecoration(salName) : undefined;

  const editCmd = (ci: number, patch: Record<string, number>) => {
    if (!section) return;
    Object.assign(section.commands[ci], patch);
    bump();
  };
  const delCmd = (ci: number) => {
    if (!section) return;
    section.commands.splice(ci, 1);
    bump();
  };
  const addSprite = () => {
    if (!section) return;
    const ti = section.commands.findIndex((c) => c.type === "terminator");
    const ins = { type: "sprite" as const, spriteIndex: 0, x: 160, y: 100, paletteOffset: 0, flags: 0 };
    if (ti >= 0) section.commands.splice(ti, 0, ins);
    else section.commands.push(ins);
    bump();
  };

  return (
    <div className="col">
      <LoadBar accept=".SAL,.sal" sampleName="PALACE.SAL" hint="Load a room file: SIET / PALACE / VILG / HARK .SAL" onLoad={loadSalFile} />

      {sal && (
        <>
          <div className="row">
            <div className="grow small muted">
              Decoration sprites:{" "}
              {decoName ? (
                <b>
                  {decoName} ({spriteCount} sprites)
                </b>
              ) : (
                <>none loaded{tip && <> — recommended: <b>{tip}</b></>}</>
              )}
            </div>
          </div>
          <LoadBar
            accept=".HSQ,.hsq"
            sampleName={tip}
            hint={tip ? `Load ${tip} to render this room's art (or any sprite sheet).` : "Load the matching decoration sprite sheet."}
            onLoad={loadDeco}
          />

          <div className="row" style={{ alignItems: "flex-start" }}>
            {/* sections */}
            <div style={{ width: 150, flexShrink: 0 }}>
              <Panel title={`${salName} — ${sal.sectionCount} rooms`}>
                <div className="scroll" style={{ maxHeight: 460 }}>
                  {sal.sections.map((s) => {
                    const c = sectionCounts(s);
                    return (
                      <div
                        key={s.index}
                        className={"clickable" + (s.index === sel ? " sel" : "")}
                        style={{ padding: "5px 8px", borderRadius: 4, cursor: "pointer", fontSize: 11 }}
                        onClick={() => setSel(s.index)}
                      >
                        <b>#{s.index}</b> <span className="muted">· {c.sprites}spr {c.polys}ply {c.rects}rct</span>
                      </div>
                    );
                  })}
                </div>
              </Panel>
            </div>

            {/* canvas */}
            <div className="grow">
              <Panel
                title={section ? `Room #${section.index} (slots ${section.spriteSlots})` : "Room"}
                right={
                  <div className="row small">
                    <label className="muted">scale</label>
                    <input type="range" min={1} max={4} value={scale} onChange={(e) => setScale(+e.target.value)} />
                    {(["sprites", "polys", "rects"] as const).map((k) => (
                      <label key={k} className="muted">
                        <input type="checkbox" checked={show[k]} onChange={(e) => setShow({ ...show, [k]: e.target.checked })} /> {k}
                      </label>
                    ))}
                    <input type="color" value={bg} onChange={(e) => setBg(e.target.value)} title="background" />
                    <button className="btn primary" onClick={() => sal && downloadBytes(salName || "SCENE.SAL", encodeSal(sal.sections))}>
                      ⤓ Export .SAL
                    </button>
                  </div>
                }
              >
                {section && (
                  <RoomCanvas section={section} sprites={sprites} palette={palette} scale={scale} show={show} bg={bg} rev={rev.current} />
                )}
                {!sprites && (
                  <div className="small muted" style={{ marginTop: 8 }}>
                    Load a decoration sheet above to render the room's art. Polygons/rects are drawn as a geometry preview
                    (exact shading isn't reproduced yet); sprite layers are exact.
                  </div>
                )}
              </Panel>
            </div>

            {/* command editor */}
            <div style={{ width: 290, flexShrink: 0 }}>
              <Panel
                title="Layout commands"
                accent="var(--blue)"
                right={
                  <button className="btn small" onClick={addSprite}>
                    + sprite
                  </button>
                }
              >
                <div className="scroll" style={{ maxHeight: 440 }}>
                  {section?.commands.map((cmd, ci) => {
                    if (cmd.type === "sprite") {
                      return (
                        <div key={ci} style={{ borderBottom: "1px solid #1e1a14", padding: "6px 0" }}>
                          <div className="row small" style={{ justifyContent: "space-between" }}>
                            <Tag color="var(--amber)">sprite</Tag>
                            <button className="btn small" onClick={() => delCmd(ci)}>
                              ✕
                            </button>
                          </div>
                          <div className="row" style={{ gap: 4, marginTop: 4 }}>
                            <NumberField label="idx" value={cmd.spriteIndex} min={-1} max={511} onChange={(v) => editCmd(ci, { spriteIndex: v })} style={{ width: 58 }} />
                            <NumberField label="x" value={cmd.x} max={511} onChange={(v) => editCmd(ci, { x: v })} style={{ width: 58 }} />
                            <NumberField label="y" value={cmd.y} max={255} onChange={(v) => editCmd(ci, { y: v })} style={{ width: 58 }} />
                            <NumberField label="pal" value={cmd.paletteOffset} max={255} onChange={(v) => editCmd(ci, { paletteOffset: v })} style={{ width: 58 }} />
                          </div>
                        </div>
                      );
                    }
                    if (cmd.type === "rect_fill") {
                      return (
                        <div key={ci} style={{ borderBottom: "1px solid #1e1a14", padding: "6px 0" }}>
                          <div className="row small" style={{ justifyContent: "space-between" }}>
                            <Tag color="var(--green)">rect {hex(cmd.header & 0xff)}</Tag>
                            <button className="btn small" onClick={() => delCmd(ci)}>
                              ✕
                            </button>
                          </div>
                          <div className="row" style={{ gap: 4, marginTop: 4 }}>
                            <NumberField label="x1" value={cmd.x1} onChange={(v) => editCmd(ci, { x1: v })} style={{ width: 58 }} />
                            <NumberField label="y1" value={cmd.y1} onChange={(v) => editCmd(ci, { y1: v })} style={{ width: 58 }} />
                            <NumberField label="x2" value={cmd.x2} onChange={(v) => editCmd(ci, { x2: v })} style={{ width: 58 }} />
                            <NumberField label="y2" value={cmd.y2} onChange={(v) => editCmd(ci, { y2: v })} style={{ width: 58 }} />
                          </div>
                        </div>
                      );
                    }
                    if (cmd.type === "polygon") {
                      return (
                        <div key={ci} className="small" style={{ borderBottom: "1px solid #1e1a14", padding: "6px 0", color: "var(--muted)" }}>
                          <Tag color="var(--purple)">poly {hex(cmd.polyType)}/{hex(cmd.polySubtype)}</Tag>{" "}
                          {cmd.verticesPass1.length + cmd.verticesPass2.length} verts · init ({cmd.initX},{cmd.initY})
                        </div>
                      );
                    }
                    return null;
                  })}
                </div>
              </Panel>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
