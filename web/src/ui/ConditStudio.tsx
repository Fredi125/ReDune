import { useEffect, useMemo, useRef, useState } from "react";
import { hsqCompress } from "../codecs/compression";
import { bytesToHex, compileExpr, conditEntries, loadCondit, type ConditEntry, type ConditFile } from "../codecs/condit";
import { countSprites, looksLikeSprite } from "../codecs/sprite";
import { downloadBytes, hex, LoadBar, Panel, Tag } from "./shared";

function compileSafe(expr: string): { bytes?: Uint8Array; error?: string } {
  try {
    return { bytes: compileExpr(expr) };
  } catch (e) {
    return { error: String(e) };
  }
}

export function ConditStudio() {
  const [name, setName] = useState("");
  const [cf, setCf] = useState<ConditFile | null>(null);
  const workRef = useRef<Uint8Array | null>(null);
  const [patched, setPatched] = useState<Set<number>>(new Set());
  const [sel, setSel] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [editExpr, setEditExpr] = useState("");
  const [play, setPlay] = useState("byte[GameStage] == 0x50");
  const [, setVer] = useState(0);

  const load = (n: string, bytes: Uint8Array) => {
    try {
      const f = loadCondit(bytes);
      setCf(f);
      workRef.current = f.data.slice();
      setName(n);
      setPatched(new Set());
      setSel(null);
      setVer((v) => v + 1);
    } catch (e) {
      alert("Could not parse CONDIT: " + e);
    }
  };

  const entries = useMemo<ConditEntry[]>(() => (cf ? conditEntries(cf, true).filter((e) => !e.empty) : []), [cf]);

  // Detect when the loaded file isn't actually CONDIT bytecode (e.g. a sprite
  // sheet) so we can warn instead of showing meaningless "expressions".
  const mismatch = useMemo(() => {
    if (!cf) return null;
    if (looksLikeSprite(cf.data)) {
      return { kind: "sprite" as const, sprites: countSprites(cf.data) };
    }
    // Real CONDIT entries are small; runaway sizes mean we're misreading data.
    const huge = entries.length > 0 && entries.filter((e) => e.sizeExec > 256).length / entries.length > 0.3;
    if (huge) return { kind: "notcondit" as const };
    return null;
  }, [cf, entries]);

  const rate = useMemo(() => {
    if (!cf) return null;
    let pass = 0;
    for (const e of entries) {
      const orig = cf.data.subarray(e.offset, e.offset + e.sizeExec);
      const r = compileSafe(e.expr);
      if (r.bytes && r.bytes.length === orig.length && r.bytes.every((b, i) => b === orig[i])) pass++;
    }
    return { pass, total: entries.length };
  }, [cf, entries]);

  useEffect(() => {
    if (sel === null) return;
    const e = entries.find((x) => x.index === sel);
    setEditExpr(e ? e.expr : "");
  }, [sel, entries]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter((e) => e.expr.toLowerCase().includes(q) || String(e.index) === q || hex(e.offset, 4).toLowerCase().includes(q));
  }, [entries, search]);

  const selEntry = sel !== null ? entries.find((e) => e.index === sel) : undefined;
  const editResult = selEntry ? compileSafe(editExpr) : { error: "" };
  const playResult = compileSafe(play);

  const canPatch =
    selEntry && editResult.bytes && editResult.bytes.length === selEntry.sizeExec && workRef.current;

  const applyPatch = () => {
    if (!selEntry || !editResult.bytes || !workRef.current) return;
    const data = workRef.current;
    for (let i = 0; i < editResult.bytes.length; i++) data[selEntry.offset + i] = editResult.bytes[i];
    const next = new Set(patched);
    next.add(selEntry.index);
    setPatched(next);
    setVer((v) => v + 1);
  };

  const exportCondit = () => {
    if (!workRef.current) return;
    downloadBytes(name || "CONDIT.HSQ", hsqCompress(workRef.current));
  };

  return (
    <div className="col">
      <LoadBar accept=".HSQ,.hsq" sampleName="CONDIT.HSQ" hint="Load CONDIT.HSQ to browse, decompile and recompile event conditions." onLoad={load} />

      <Panel title="Recompiler playground" accent="var(--purple)">
        <div className="row">
          <input className="grow mono" value={play} onChange={(e) => setPlay(e.target.value)} placeholder="byte[GameStage] >= 0x38 & word[0x10] != 0x00" />
        </div>
        <div style={{ marginTop: 8 }}>
          {playResult.bytes ? (
            <div className="hexbox">
              {bytesToHex(playResult.bytes)} <span className="muted">({playResult.bytes.length} bytes)</span>
            </div>
          ) : (
            <div className="warn small">{playResult.error}</div>
          )}
        </div>
        <div className="small muted" style={{ marginTop: 6 }}>
          Operands: <code>byte[Name|0xNN]</code>, <code>word[…]</code>, <code>0xNN</code>. Ops: == != &lt; &gt; &lt;= &gt;= + - &amp; | (named vars like GameStage resolve automatically).
        </div>
      </Panel>

      {cf && mismatch && (
        <div className="panel" style={{ borderColor: "var(--red)" }}>
          <div className="panel-b small">
            {mismatch.kind === "sprite" ? (
              <>
                <span className="warn">
                  <b>This isn't CONDIT.HSQ.</b>
                </span>{" "}
                It parses as a <b>sprite sheet ({mismatch.sprites} sprites)</b>, so the entries below are meaningless —
                the CONDIT decoder will read any HSQ as bytecode. Open <b>{name}</b> in the <b>Sprites</b> tab to view it,
                and load the real <code>CONDIT.HSQ</code> here for actual event conditions.
              </>
            ) : (
              <>
                <span className="warn">
                  <b>This doesn't look like CONDIT bytecode.</b>
                </span>{" "}
                Entry sizes are implausibly large, so the decompiled output is unreliable. Make sure you loaded{" "}
                <code>CONDIT.HSQ</code>.
              </>
            )}
          </div>
        </div>
      )}

      {cf && (
        <div className="row" style={{ alignItems: "flex-start" }}>
          <div className="grow">
            <Panel
              title={`${name} — ${cf.entryCount} entries, ${entries.length} non-empty`}
              right={
                <div className="row small">
                  {rate && <span className="muted">roundtrip {((100 * rate.pass) / rate.total).toFixed(1)}%</span>}
                  {patched.size > 0 && <Tag color="var(--amber)">{patched.size} patched</Tag>}
                  <button className="btn" disabled={patched.size === 0} onClick={exportCondit}>
                    ⤓ Export CONDIT.HSQ
                  </button>
                </div>
              }
            >
              <input className="grow mono" style={{ width: "100%", marginBottom: 8 }} placeholder="search expression / index / offset…" value={search} onChange={(e) => setSearch(e.target.value)} />
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Offset</th>
                      <th>Sz</th>
                      <th>Expression</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.slice(0, 400).map((e) => (
                      <tr key={e.index} className={"clickable" + (e.index === sel ? " sel" : "")} onClick={() => setSel(e.index)}>
                        <td className="muted">
                          {e.index}
                          {patched.has(e.index) && " *"}
                        </td>
                        <td className="muted small">{hex(e.offset, 4)}</td>
                        <td className="muted small">{e.sizeExec}{e.overflow ? "!" : ""}</td>
                        <td className="small" style={{ color: "var(--blue)" }}>{e.expr}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filtered.length > 400 && <div className="small muted" style={{ padding: 8 }}>… {filtered.length - 400} more (refine search)</div>}
              </div>
            </Panel>
          </div>

          <div style={{ width: 340, flexShrink: 0 }}>
            {selEntry ? (
              <Panel title={`Entry ${selEntry.index}`} accent="var(--purple)">
                <div className="col">
                  <div className="small muted">
                    offset {hex(selEntry.offset, 4)} · exec {selEntry.sizeExec}b{selEntry.overflow ? " · OVERFLOW (shared chain)" : ""}
                  </div>
                  <div className="hexbox small">{selEntry.rawHex}</div>
                  <div className="field">
                    <label>Expression (editable)</label>
                    <textarea className="codearea mono" value={editExpr} onChange={(e) => setEditExpr(e.target.value)} />
                  </div>
                  {editResult.bytes ? (
                    <div className="hexbox small">
                      {bytesToHex(editResult.bytes)} <span className="muted">({editResult.bytes.length}b)</span>
                    </div>
                  ) : (
                    <div className="warn small">{editResult.error}</div>
                  )}
                  <div className="row">
                    <button className="btn primary" disabled={!canPatch} onClick={applyPatch}>
                      Apply patch
                    </button>
                    {editResult.bytes && editResult.bytes.length !== selEntry.sizeExec && (
                      <span className="warn small">length must equal {selEntry.sizeExec}b to patch in place</span>
                    )}
                    {patched.has(selEntry.index) && <span className="ok small">patched ✓</span>}
                  </div>
                  {selEntry.overflow && (
                    <div className="small muted">
                      This entry's bytecode overflows its table slot — it shares a chain with later entries. Patching it may affect them.
                    </div>
                  )}
                </div>
              </Panel>
            ) : (
              <Panel title="Entry detail" accent="var(--purple)">
                <div className="muted small">Select an entry to decompile, edit and recompile it.</div>
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
