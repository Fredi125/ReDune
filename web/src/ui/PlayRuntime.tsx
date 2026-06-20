import { useMemo, useState } from "react";
import { loadDialogue, type DialogueFile } from "../codecs/dialogue";
import { conditionExpr, loadCondit, type ConditFile } from "../codecs/condit";
import { evalCondit, type VarStore } from "../codecs/conditVM";
import { displayText, loadTextTable, type TextTable } from "../codecs/text";
import { DuneSave } from "../codecs/save";
import { CONDIT_VARIABLES, GAME_STAGES } from "../codecs/constants";
import { hex, LoadBar, NumberField, Panel, Tag } from "./shared";
import { useIncoming } from "./routing";

/** Curated game-state variables worth exposing in the runtime panel. */
const KEY_VARS: number[] = [0x2a, 0x2b, 0x23, 0x10, 0x12, 0x02, 0x0a, 0x0b, 0x90, 0xbf, 0xc2, 0xfb];

export function PlayRuntime() {
  const [dlg, setDlg] = useState<DialogueFile | null>(null);
  const [cf, setCf] = useState<ConditFile | null>(null);
  const [phr, setPhr] = useState<TextTable | null>(null);
  const [store, setStore] = useState<VarStore>(new Map());
  const [sel, setSel] = useState(0);

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
    } catch (e) {
      alert("Couldn't read save: " + e);
    }
  };

  useIncoming("play", (n, b) => {
    const u = n.toUpperCase();
    try {
      if (u.includes("CONDIT")) setCf(loadCondit(b));
      else if (u.includes("PHRASE")) setPhr(loadTextTable(b));
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
          <LoadBar accept=".SAV,.sav" sampleName="SampleSave.SAV" hint="Optional: a save to seed GameStage." onLoad={(_, b) => seedFromSave(b)} />
        </div>
      </div>

      {dlg && cf && (
        <div className="row" style={{ alignItems: "flex-start" }}>
          {/* game-state editor */}
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
            <Panel
              title={entry ? `Entry #${entry.entry} — ${availCount}/${entry.records.length} available now` : "Dialogue"}
              accent="var(--blue)"
            >
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
      )}
    </div>
  );
}
