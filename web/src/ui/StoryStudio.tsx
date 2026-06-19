import { useMemo, useState } from "react";
import { exportDialogueHsq, loadDialogue, refreshRecord, type DialogueFile, type DialogueRecord } from "../codecs/dialogue";
import { conditionExpr, loadCondit, type ConditFile } from "../codecs/condit";
import { displayText, loadTextTable, type TextTable } from "../codecs/text";
import { downloadBytes, hex, LoadBar, NumberField, Panel, Tag } from "./shared";
import { useIncoming } from "./routing";

export function StoryStudio() {
  const [dlg, setDlg] = useState<DialogueFile | null>(null);
  const [cf, setCf] = useState<ConditFile | null>(null);
  const [phr, setPhr] = useState<TextTable | null>(null);
  const [phrName, setPhrName] = useState("");
  const [sel, setSel] = useState(0);
  const [search, setSearch] = useState("");
  const [, setVer] = useState(0);
  const editRaw = (r: DialogueRecord, fn: () => void) => {
    fn();
    refreshRecord(r);
    setVer((v) => v + 1);
  };

  const phraseText = (idx: number): string | null => {
    if (!phr) return null;
    const e = phr.entries[idx];
    return e ? displayText(e.raw) : `<phrase ${hex(idx, 3)} missing>`;
  };
  const condExpr = (idx: number): string | null => (cf ? conditionExpr(cf, idx) : null);

  // Auto-detect sends DIALOGUE here; also accept a CONDIT/PHRASE drop by name.
  useIncoming("story", (n, b) => {
    const u = n.toUpperCase();
    try {
      if (u.includes("CONDIT")) setCf(loadCondit(b));
      else if (u.includes("PHRASE")) {
        setPhr(loadTextTable(b));
        setPhrName(n);
      } else setDlg(loadDialogue(b));
    } catch (e) {
      alert("Couldn't load into Story: " + e);
    }
  });

  const nonEmpty = useMemo(() => (dlg ? dlg.entries.filter((e) => e.records.length > 0) : []), [dlg]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return nonEmpty;
    return nonEmpty.filter((e) => {
      if (String(e.entry) === q) return true;
      if (!phr) return false;
      return e.records.some((r) => (phraseText(r.phraseIdx) || "").toLowerCase().includes(q));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonEmpty, search, phr]);

  const entry = dlg && nonEmpty.find((e) => e.entry === sel) ? dlg.entries[sel] : nonEmpty[0];

  return (
    <div className="col">
      <LoadBar accept=".HSQ,.hsq" sampleName="DIALOGUE.HSQ" hint="Load DIALOGUE.HSQ (required) — the dialogue script table." onLoad={(_, b) => { try { setDlg(loadDialogue(b)); } catch (e) { alert("Not DIALOGUE.HSQ: " + e); } }} />
      <div className="row">
        <div className="grow">
          <LoadBar accept=".HSQ,.hsq" sampleName="CONDIT.HSQ" hint={cf ? "CONDIT loaded ✓ — conditions resolved." : "Optional: load CONDIT.HSQ to show each option's condition."} onLoad={(_, b) => { try { setCf(loadCondit(b)); } catch (e) { alert("Not CONDIT.HSQ: " + e); } }} />
        </div>
        <div className="grow">
          <LoadBar accept=".HSQ,.hsq" sampleName="PHRASE11.HSQ" hint={phr ? `${phrName} loaded ✓ — phrase text resolved.` : "Optional: load PHRASE{lang}1.HSQ (bank 0) to show the actual text."} onLoad={(n, b) => { try { setPhr(loadTextTable(b)); setPhrName(n); } catch (e) { alert("Not a PHRASE table: " + e); } }} />
        </div>
      </div>

      {dlg && (
        <div className="row" style={{ alignItems: "flex-start" }}>
          <div style={{ width: 200, flexShrink: 0 }}>
            <Panel title={`Dialogue — ${nonEmpty.length}/${dlg.entryCount} entries`}>
              <input className="grow mono" style={{ width: "100%", marginBottom: 8 }} placeholder={phr ? "search text / entry#" : "search entry#"} value={search} onChange={(e) => setSearch(e.target.value)} />
              <div className="scroll" style={{ maxHeight: 460 }}>
                {filtered.map((e) => (
                  <div key={e.entry} className={"clickable" + (entry && e.entry === entry.entry ? " sel" : "")} style={{ padding: "5px 8px", borderRadius: 4, fontSize: 11 }} onClick={() => setSel(e.entry)}>
                    <b>#{e.entry}</b> <span className="muted">· {e.records.length} opt</span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>

          <div className="grow">
            <Panel
              title={entry ? `Entry #${entry.entry} — ${entry.records.length} options` : "Dialogue entry"}
              accent="var(--purple)"
              right={dlg ? <button className="btn primary" onClick={() => downloadBytes("DIALOGUE.HSQ", exportDialogueHsq(dlg.entries))}>⤓ Export DIALOGUE.HSQ</button> : undefined}
            >
              {!cf && <div className="small muted" style={{ marginBottom: 8 }}>Load CONDIT.HSQ to resolve conditions; PHRASE to resolve text. Fields below are editable.</div>}
              <div className="scroll" style={{ maxHeight: 480 }}>
                {entry?.records.map((r, i) => {
                  const expr = condExpr(r.conditIdx);
                  const text = phraseText(r.phraseIdx);
                  return (
                    <div key={i} style={{ borderBottom: "1px solid #1e1a14", padding: "8px 0" }}>
                      <div className="row small" style={{ gap: 4 }}>
                        <Tag color="var(--purple)">opt {i}</Tag>
                        {r.spoken && <Tag color="var(--dim)">spoken</Tag>}
                        {r.repeatable && <Tag color="var(--blue)">repeat</Tag>}
                        {!!r.menuFlag && <Tag color="var(--amber)">menu</Tag>}
                        {!!r.actionCode && <Tag color="var(--green)">act {r.actionCode}</Tag>}
                      </div>
                      <div className="small" style={{ marginTop: 4 }}>
                        <span className="muted">IF</span>{" "}
                        <span style={{ color: "var(--blue)" }}>
                          CONDIT[{r.conditIdx}]{r.condType ? ` (type${r.condType})` : ""}
                          {expr !== null ? `: ${expr}` : ""}
                        </span>
                      </div>
                      <div className="small" style={{ marginTop: 2 }}>
                        <span className="muted">SAY</span> <span className="muted">phrase {hex(r.phraseIdx, 3)}:</span>{" "}
                        {text !== null ? <span style={{ color: "var(--text)" }}>“{text}”</span> : <span className="muted">(load PHRASE to see text)</span>}
                      </div>
                      <div className="row" style={{ gap: 4, marginTop: 4, alignItems: "flex-end" }}>
                        <NumberField label="NPC" value={r.npcId} max={255} onChange={(v) => editRaw(r, () => (r.raw[1] = v & 0xff))} style={{ width: 64 }} />
                        <div className="field" style={{ width: 56 }}>
                          <label>type</label>
                          <select value={r.condType} onChange={(e) => editRaw(r, () => (r.raw[2] = (r.raw[2] & ~0xc0) | ((+e.target.value & 3) << 6)))}>
                            {[0, 1, 2, 3].map((t) => (<option key={t} value={t}>{t}</option>))}
                          </select>
                        </div>
                        <NumberField label="phrase" value={r.phraseIdx} max={1023} onChange={(v) => editRaw(r, () => { r.raw[2] = (r.raw[2] & ~0x03) | ((v >> 8) & 3); r.raw[3] = v & 0xff; })} style={{ width: 76 }} />
                        <label className="small muted"><input type="checkbox" checked={r.spoken} onChange={(e) => editRaw(r, () => (r.raw[0] = (r.raw[0] & ~0x80) | (e.target.checked ? 0x80 : 0)))} /> spoken</label>
                        <label className="small muted"><input type="checkbox" checked={r.repeatable} onChange={(e) => editRaw(r, () => (r.raw[0] = (r.raw[0] & ~0x40) | (e.target.checked ? 0x40 : 0)))} /> repeat</label>
                        <label className="small muted"><input type="checkbox" checked={!!r.menuFlag} onChange={(e) => editRaw(r, () => (r.raw[2] = (r.raw[2] & ~0x0c) | (e.target.checked ? 0x04 : 0)))} /> menu</label>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
