import { useMemo, useState } from "react";
import { loadDialogue, type DialogueFile } from "../codecs/dialogue";
import { conditionExpr, loadCondit, type ConditFile } from "../codecs/condit";
import { evalCondit, type VarStore } from "../codecs/conditVM";
import { displayText, loadTextTable, type TextTable } from "../codecs/text";
import { DuneSave, type NPC } from "../codecs/save";
import { loadSal, type SalFile } from "../codecs/sal";
import { loadSpriteFile, type RGB } from "../codecs/sprite";
import { loadGradientTables, type GradTable } from "../codecs/globdata";
import { CONDIT_VARIABLES, GAME_STAGES, recommendedDecoration } from "../codecs/constants";
import { hex, LoadBar, NumberField, Panel, Tag } from "./shared";
import { useIncoming } from "./routing";
import { buildSpriteCanvases, RoomCanvas } from "./RoomCanvas";

/** Curated game-state variables worth exposing in the runtime panel. */
const KEY_VARS: number[] = [0x2a, 0x2b, 0x23, 0x10, 0x12, 0x02, 0x0a, 0x0b, 0x90, 0xbf, 0xc2, 0xfb];

export function PlayRuntime() {
  const [dlg, setDlg] = useState<DialogueFile | null>(null);
  const [cf, setCf] = useState<ConditFile | null>(null);
  const [phr, setPhr] = useState<TextTable | null>(null);
  const [store, setStore] = useState<VarStore>(new Map());
  const [sel, setSel] = useState(0);
  const [npcs, setNpcs] = useState<NPC[] | null>(null);

  // Optional scene backdrop (reuses the Rooms compositor).
  const [sal, setSal] = useState<SalFile | null>(null);
  const [salName, setSalName] = useState("");
  const [section, setSection] = useState(0);
  const [sprites, setSprites] = useState<(HTMLCanvasElement | null)[] | null>(null);
  const [palette, setPalette] = useState<Map<number, RGB> | null>(null);
  const [gradTables, setGradTables] = useState<GradTable[] | null>(null);
  const [showBackdrop, setShowBackdrop] = useState(false);

  const setVar = (idx: number, val: number) => {
    setStore((prev) => {
      const n = new Map(prev);
      n.set(idx, val & 0xffff);
      return n;
    });
  };

  const seedFromSave = (bytes: Uint8Array) => {
    try {
      const s = new DuneSave(bytes);
      setVar(0x2a, s.gameStage); // GameStage is the mapping we can trust
      setNpcs(s.allNpcs());
    } catch (e) {
      alert("Couldn't read save: " + e);
    }
  };

  const loadSalFile = (n: string, bytes: Uint8Array) => {
    try {
      setSal(loadSal(bytes));
      setSalName(n);
      setSection(0);
      setShowBackdrop(true);
    } catch (e) {
      alert("Not a SAL room: " + e);
    }
  };

  useIncoming("play", (n, b) => {
    const u = n.toUpperCase();
    try {
      if (u.includes("CONDIT")) setCf(loadCondit(b));
      else if (u.includes("PHRASE")) setPhr(loadTextTable(b));
      else if (u.endsWith(".SAL")) loadSalFile(n, b);
      else if (u.endsWith(".SAV")) seedFromSave(b);
      else setDlg(loadDialogue(b));
    } catch (e) {
      alert("Couldn't load into Play: " + e);
    }
  });

  const phraseText = (idx: number): string | null => {
    if (!phr) return null;
    const e = phr.entries[idx];
    return e ? displayText(e.raw) : null;
  };

  const nonEmpty = useMemo(() => (dlg ? dlg.entries.filter((e) => e.records.length > 0) : []), [dlg]);
  const entry = dlg && nonEmpty.find((e) => e.entry === sel) ? dlg.entries[sel] : nonEmpty[0];

  // Live availability of the selected entry's options against the current state.
  const evals = useMemo(() => {
    if (!cf || !entry) return [];
    return entry.records.map((r) => ({ rec: r, available: evalCondit(cf, r.conditIdx, store) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cf, entry, store]);
  const availCount = evals.filter((e) => e.available).length;
  const stageVal = store.get(0x2a) ?? 0;
  const decoTip = sal ? recommendedDecoration(salName) : "";

  return (
    <div className="col">
      <LoadBar accept=".HSQ,.hsq" sampleName="DIALOGUE.HSQ" hint="Load DIALOGUE.HSQ (required) — the dialogue script." onLoad={(_, b) => { try { setDlg(loadDialogue(b)); } catch (e) { alert("Not DIALOGUE.HSQ: " + e); } }} />
      <div className="row">
        <div className="grow">
          <LoadBar accept=".HSQ,.hsq" sampleName="CONDIT.HSQ" hint={cf ? "CONDIT loaded ✓ — conditions are evaluated live." : "Load CONDIT.HSQ (required) — the condition VM."} onLoad={(_, b) => { try { setCf(loadCondit(b)); } catch (e) { alert("Not CONDIT.HSQ: " + e); } }} />
        </div>
        <div className="grow">
          <LoadBar accept=".HSQ,.hsq" sampleName="PHRASE11.HSQ" hint={phr ? "PHRASE loaded ✓ — spoken lines shown." : "Optional: PHRASE{lang}1.HSQ for the spoken text."} onLoad={(_, b) => { try { setPhr(loadTextTable(b)); } catch (e) { alert("Not a PHRASE table: " + e); } }} />
        </div>
        <div className="grow">
          <LoadBar accept=".SAV,.sav" sampleName="SampleSave.SAV" hint={npcs ? `Save loaded ✓ — ${npcs.length} NPCs.` : "Optional: a save to seed GameStage + list NPCs."} onLoad={(_, b) => seedFromSave(b)} />
        </div>
      </div>

      {dlg && cf && (
        <>
          {/* optional scene backdrop */}
          <Panel
            title="Scene backdrop (optional)"
            right={<button className="btn small" onClick={() => setShowBackdrop((v) => !v)}>{showBackdrop ? "hide" : "show"}</button>}
          >
            {showBackdrop && (
              <div className="row" style={{ alignItems: "flex-start" }}>
                <div style={{ width: 320, flexShrink: 0 }}>
                  <LoadBar accept=".SAL,.sal" sampleName="PALACE.SAL" hint="Load a room: SIET / PALACE / VILG / HARK .SAL" onLoad={loadSalFile} />
                  {sal && (
                    <LoadBar
                      accept=".HSQ,.hsq"
                      sampleName={decoTip || "MIRROR.HSQ"}
                      hint={decoTip ? `Load ${decoTip} for this room's art (+ GLOBDATA for gradients).` : "Load the decoration sheet."}
                      onLoad={(_, b) => {
                        try {
                          const sf = loadSpriteFile(b);
                          setSprites(buildSpriteCanvases(sf));
                          setPalette(sf.palette);
                        } catch (e) {
                          alert("Not a sprite sheet: " + e);
                        }
                      }}
                    />
                  )}
                  {sal && (
                    <LoadBar accept=".HSQ,.hsq" sampleName="GLOBDATA.HSQ" hint="Optional: GLOBDATA.HSQ for authentic polygon gradients." onLoad={(_, b) => { try { setGradTables(loadGradientTables(b)); } catch (e) { alert("Not GLOBDATA: " + e); } }} />
                  )}
                </div>
                {sal && sal.sections[section] && (
                  <div>
                    <div className="row small" style={{ marginBottom: 6 }}>
                      <label className="muted">{salName} section</label>
                      <select value={section} onChange={(e) => setSection(+e.target.value)}>
                        {sal.sections.map((_, i) => (
                          <option key={i} value={i}>#{i}</option>
                        ))}
                      </select>
                    </div>
                    <RoomCanvas section={sal.sections[section]} sprites={sprites} palette={palette} gradTables={gradTables} scale={1.5} show={{ sprites: true, polys: true, rects: true }} bg="#101018" rev={0} />
                  </div>
                )}
              </div>
            )}
          </Panel>

          <div className="row" style={{ alignItems: "flex-start" }}>
            {/* game-state editor + NPC roster */}
            <div style={{ width: 250, flexShrink: 0 }}>
              <Panel title="Game state" accent="var(--green)">
                <div className="field">
                  <label>GameStage ({hex(stageVal)})</label>
                  <select value={stageVal} onChange={(e) => setVar(0x2a, +e.target.value)}>
                    {Object.entries(GAME_STAGES).map(([v, n]) => (
                      <option key={v} value={v}>{hex(+v)} — {n}</option>
                    ))}
                    {!(stageVal in GAME_STAGES) && <option value={stageVal}>{hex(stageVal)} — (custom)</option>}
                  </select>
                </div>
                <div className="small muted" style={{ margin: "6px 0" }}>Edit any variable; options re-evaluate live.</div>
                <div className="col" style={{ gap: 4 }}>
                  {KEY_VARS.filter((i) => i !== 0x2a).map((i) => (
                    <NumberField key={i} label={`${CONDIT_VARIABLES[i] ?? hex(i)}`} value={store.get(i) ?? 0} max={65535} onChange={(v) => setVar(i, v)} />
                  ))}
                </div>
              </Panel>
              {npcs && (
                <Panel title={`NPCs (${npcs.length})`} accent="var(--amber)">
                  <div className="scroll" style={{ maxHeight: 240 }}>
                    {npcs.map((npc) => (
                      <div
                        key={npc.index}
                        className={"clickable" + (entry && entry.entry === npc.forDialogue ? " sel" : "")}
                        title={`room ${hex(npc.roomLocation)} / place ${hex(npc.typeOfPlace)} → dialogue #${npc.forDialogue}`}
                        style={{ padding: "5px 8px", borderRadius: 4, fontSize: 11 }}
                        onClick={() => setSel(npc.forDialogue)}
                      >
                        <b>{npc.spriteName}</b> <span className="muted">→ #{npc.forDialogue}</span>
                        {npc.dialogueAvailable > 0 && <span className="muted"> · dlg {npc.dialogueAvailable}</span>}
                      </div>
                    ))}
                  </div>
                  <div className="small muted" style={{ marginTop: 6 }}>Click an NPC to open the line they speak (their <code>forDialogue</code> entry).</div>
                </Panel>
              )}
            </div>

            {/* dialogue entry list */}
            <div style={{ width: 150, flexShrink: 0 }}>
              <Panel title={`Entries (${nonEmpty.length})`}>
                <div className="scroll" style={{ maxHeight: 460 }}>
                  {nonEmpty.map((e) => (
                    <div key={e.entry} className={"clickable" + (entry && e.entry === entry.entry ? " sel" : "")} style={{ padding: "5px 8px", borderRadius: 4, fontSize: 11 }} onClick={() => setSel(e.entry)}>
                      <b>#{e.entry}</b> <span className="muted">· {e.records.length}</span>
                    </div>
                  ))}
                </div>
              </Panel>
            </div>

            {/* live runtime view */}
            <div className="grow">
              <Panel title={entry ? `Entry #${entry.entry} — ${availCount}/${entry.records.length} available now` : "Dialogue"} accent="var(--blue)">
                <div className="scroll" style={{ maxHeight: 480 }}>
                  {evals.map(({ rec, available }, i) => {
                    const expr = conditionExpr(cf, rec.conditIdx);
                    const text = phraseText(rec.phraseIdx);
                    return (
                      <div key={i} style={{ borderBottom: "1px solid #1e1a14", padding: "8px 0", opacity: available ? 1 : 0.5 }}>
                        <div className="row small" style={{ gap: 6 }}>
                          {available ? <Tag color="var(--green)">● AVAILABLE</Tag> : <Tag color="var(--dim)">○ blocked</Tag>}
                          <span className="muted">opt {i}</span>
                          {rec.spoken && <Tag color="var(--dim)">spoken</Tag>}
                        </div>
                        <div className="small" style={{ marginTop: 4 }}>
                          <span className="muted">IF</span>{" "}
                          <span style={{ color: available ? "var(--green)" : "var(--blue)" }}>{expr || "(always)"}</span>
                        </div>
                        <div className="small" style={{ marginTop: 2 }}>
                          <span className="muted">SAY</span>{" "}
                          {text !== null ? <span style={{ color: "var(--text)" }}>“{text}”</span> : <span className="muted">phrase {hex(rec.phraseIdx, 3)} (load PHRASE)</span>}
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="small muted" style={{ marginTop: 8 }}>
                  The real CONDIT VM evaluates each option's gating condition against the editable game state on the left —
                  change <b>GameStage</b> or a flag and watch which lines unlock. This is the engine's dialogue-gating logic
                  running in your browser.
                </div>
              </Panel>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
