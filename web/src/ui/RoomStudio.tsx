import { useRef, useState } from "react";
import { encodeSal, loadSal, sectionCounts, type SalFile } from "../codecs/sal";
import { loadSpriteFile, type RGB, type SpriteFile } from "../codecs/sprite";
import { loadGradientTables, type GradTable } from "../codecs/globdata";
import { recommendedDecoration } from "../codecs/constants";
import { downloadBytes, hex, LoadBar, NumberField, Panel, Tag } from "./shared";
import { useIncoming } from "./routing";
import { buildSpriteCanvases, RoomCanvas } from "./RoomCanvas";
import { useTint } from "./tint";

export function RoomStudio() {
  const tint = useTint();
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
  const [gradTables, setGradTables] = useState<GradTable[] | null>(null);
  const [gradName, setGradName] = useState("");

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

  const loadGrad = (n: string, bytes: Uint8Array) => {
    try {
      setGradTables(loadGradientTables(bytes));
      setGradName(n);
      bump();
    } catch (e) {
      alert("Not GLOBDATA.HSQ: " + e);
    }
  };

  useIncoming("rooms", loadSalFile);

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
          <LoadBar
            accept=".HSQ,.hsq"
            sampleName="GLOBDATA.HSQ"
            hint={gradTables ? `${gradName} loaded ✓ — polygons shaded with real gradient ramps.` : "Optional: load GLOBDATA.HSQ for authentic polygon gradient shading."}
            onLoad={loadGrad}
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
                  <RoomCanvas section={section} sprites={sprites} palette={palette} gradTables={gradTables} scale={scale} show={show} bg={bg} rev={rev.current} filter={tint.filter} />
                )}
                <div style={{ marginTop: 8 }}>{tint.controls}</div>
                <div className="small muted" style={{ marginTop: 8 }}>
                  Load a decoration sheet to render sprite art. With GLOBDATA.HSQ + the decoration sheet, polygons are
                  filled with their real vertical gradient ramps (subtype → gradient table → room palette). Note: SAL
                  sprite indices beyond the loaded sheet's sprite count are skipped (load the matching decoration sheet
                  to fill them in).
                </div>
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
