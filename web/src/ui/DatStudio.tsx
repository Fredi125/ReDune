import { useMemo, useRef, useState } from "react";
import { entryIsHsq, extractFile, parseDat, rebuildDat, type DatFile } from "../codecs/dat";
import { hsqDecompress } from "../codecs/compression";
import { downloadBytes, hex, LoadBar, Panel, Tag } from "./shared";
import { useIncoming } from "./routing";

export function DatStudio() {
  const [dat, setDat] = useState<DatFile | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const replRef = useRef<Map<string, Uint8Array>>(new Map());
  const [, setVer] = useState(0);
  const bump = () => setVer((v) => v + 1);
  const fileInput = useRef<HTMLInputElement>(null);
  const replaceTarget = useRef<string | null>(null);

  const load = (_: string, bytes: Uint8Array) => {
    setError("");
    try {
      setDat(parseDat(bytes));
      replRef.current = new Map();
      bump();
    } catch (e) {
      setDat(null);
      setError(String(e));
    }
  };

  useIncoming("archive", load);

  const filtered = useMemo(() => {
    if (!dat) return [];
    const q = search.trim().toLowerCase();
    return q ? dat.entries.filter((e) => e.name.toLowerCase().includes(q)) : dat.entries;
  }, [dat, search]);

  const safe = (name: string) => name.replace(/[\\/]/g, "_");

  const doExtract = (name: string, decompress: boolean) => {
    if (!dat) return;
    const e = dat.entries.find((x) => x.name === name);
    if (!e) return;
    let bytes = extractFile(dat, e);
    let out = safe(name);
    if (decompress) {
      try {
        bytes = hsqDecompress(bytes);
        out = out.replace(/\.[^.]+$/, "") + ".bin";
      } catch {
        /* fall back to raw */
      }
    }
    downloadBytes(out, bytes);
  };

  const startReplace = (name: string) => {
    replaceTarget.current = name;
    fileInput.current?.click();
  };

  const onReplaceFile = (file: File) => {
    const name = replaceTarget.current;
    if (!name) return;
    const r = new FileReader();
    r.onload = () => {
      replRef.current.set(name, new Uint8Array(r.result as ArrayBuffer));
      bump();
    };
    r.readAsArrayBuffer(file);
  };

  const repl = replRef.current;

  return (
    <div className="col">
      <LoadBar
        accept=".DAT,.dat"
        hint="Load DUNE.DAT (the master archive, ~25 MB). Everything stays in your browser. (Not bundled — use your own.)"
        onLoad={load}
      />
      {error && <div className="warn small">Not a DUNE.DAT archive: {error}</div>}
      <input ref={fileInput} type="file" style={{ display: "none" }} onChange={(e) => e.target.files?.[0] && onReplaceFile(e.target.files[0])} />

      {dat && (
        <Panel
          title={`DUNE.DAT — ${dat.entries.length} files · magic ${hex(dat.magic, 4)}`}
          right={
            <div className="row small">
              {repl.size > 0 && <Tag color="var(--amber)">{repl.size} replaced</Tag>}
              <button className="btn" disabled={repl.size === 0} onClick={() => { replRef.current = new Map(); bump(); }}>
                clear
              </button>
              <button className="btn primary" onClick={() => downloadBytes("DUNE.DAT", rebuildDat(dat, repl))}>
                ⤓ Rebuild &amp; download DUNE.DAT
              </button>
            </div>
          }
        >
          <div className="small muted" style={{ marginBottom: 8 }}>
            Closes the mod loop: <b>Extract</b> an asset, edit it in another tab (Rooms/Text/Sprites), then{" "}
            <b>Replace</b> it here and rebuild a working archive. Replacements are matched by name.
          </div>
          <input className="grow mono" style={{ width: "100%", marginBottom: 8 }} placeholder="search filename…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Size</th>
                  <th>Type</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 500).map((e) => {
                  const replaced = repl.has(e.name);
                  const hsq = entryIsHsq(dat, e);
                  return (
                    <tr key={e.name} className={sel === e.name ? "sel" : ""} onClick={() => setSel(e.name)}>
                      <td className="small">
                        {e.name}
                        {replaced && <Tag color="var(--amber)"> replaced</Tag>}
                      </td>
                      <td className="muted small">{(replaced ? repl.get(e.name)!.length : e.size).toLocaleString()}</td>
                      <td className="small">{hsq ? <Tag color="var(--blue)">HSQ</Tag> : <span className="muted">raw</span>}</td>
                      <td>
                        <div className="row small" style={{ gap: 4 }}>
                          <button className="btn small" onClick={() => doExtract(e.name, false)}>
                            extract
                          </button>
                          {hsq && (
                            <button className="btn small" onClick={() => doExtract(e.name, true)}>
                              decompress
                            </button>
                          )}
                          <button className="btn small" onClick={() => startReplace(e.name)}>
                            replace…
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filtered.length > 500 && <div className="small muted" style={{ padding: 8 }}>… {filtered.length - 500} more (refine search)</div>}
          </div>
        </Panel>
      )}
    </div>
  );
}
