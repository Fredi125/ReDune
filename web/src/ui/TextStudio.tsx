import { useMemo, useRef, useState } from "react";
import { editableToBytes, exportTextHsq, loadTextTable, type TextTable } from "../codecs/text";
import { downloadBytes, LoadBar, Panel } from "./shared";

export function TextStudio() {
  const tblRef = useRef<TextTable | null>(null);
  const [name, setName] = useState("");
  const [, setVer] = useState(0);
  const bump = () => setVer((v) => v + 1);
  const [sel, setSel] = useState(0);
  const [search, setSearch] = useState("");

  const load = (n: string, bytes: Uint8Array) => {
    try {
      tblRef.current = loadTextTable(bytes);
      setName(n);
      setSel(0);
      bump();
    } catch (e) {
      alert("Not a PHRASE/COMMAND string table: " + e);
    }
  };

  const tbl = tblRef.current;
  const filtered = useMemo(() => {
    if (!tbl) return [];
    const q = search.trim().toLowerCase();
    if (!q) return tbl.entries;
    return tbl.entries.filter((e) => e.text.toLowerCase().includes(q) || String(e.index) === q);
  }, [tbl, search, setVer]);

  const entry = tbl && sel < tbl.entries.length ? tbl.entries[sel] : null;

  return (
    <div className="col">
      <LoadBar accept=".HSQ,.hsq" sampleName="COMMAND1.HSQ" hint="Load a text table: PHRASE*.HSQ (dialogue) or COMMAND*.HSQ (UI strings)." onLoad={load} />

      {tbl && (
        <div className="row" style={{ alignItems: "flex-start" }}>
          <div className="grow">
            <Panel
              title={`${name} — ${tbl.count} strings`}
              right={
                <button className="btn primary" onClick={() => downloadBytes(name || "TEXT.HSQ", exportTextHsq(tbl.entries))}>
                  ⤓ Export .HSQ
                </button>
              }
            >
              <input className="grow mono" style={{ width: "100%", marginBottom: 8 }} placeholder="search text / index…" value={search} onChange={(e) => setSearch(e.target.value)} />
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Text</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.slice(0, 600).map((e) => (
                      <tr key={e.index} className={"clickable" + (e.index === sel ? " sel" : "")} onClick={() => setSel(e.index)}>
                        <td className="muted">{e.index}</td>
                        <td className="small">{e.text.length > 90 ? e.text.slice(0, 90) + "…" : e.text || <span className="muted">(empty)</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filtered.length > 600 && <div className="small muted" style={{ padding: 8 }}>… {filtered.length - 600} more (refine search)</div>}
              </div>
            </Panel>
          </div>

          <div style={{ width: 360, flexShrink: 0 }}>
            <Panel title={entry ? `String ${entry.index}` : "String"} accent="var(--blue)">
              {entry && (
                <div className="col">
                  <textarea
                    className="codearea mono"
                    style={{ minHeight: 140 }}
                    value={entry.text}
                    onChange={(e) => {
                      entry.text = e.target.value;
                      bump();
                    }}
                  />
                  <div className="small muted">{editableToBytes(entry.text).length} bytes encoded</div>
                  <div className="small muted">
                    <code>|</code> = variant separator (0xFF). <code>{"{XX}"}</code> = control byte (hex). A literal{" "}
                    <code>{"{"}</code>/<code>|</code> is shown escaped. Edits re-pack into a working HSQ on export.
                  </div>
                </div>
              )}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
