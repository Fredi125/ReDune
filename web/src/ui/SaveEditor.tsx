import { useRef, useState } from "react";
import { DuneSave } from "../codecs/save";
import { EQUIPMENT_FLAGS, GAME_STAGES, SIETCH_STATUS_FLAGS, TROOP_JOBS } from "../codecs/constants";
import { downloadBytes, hex, LoadBar, NumberField, Panel, Tag } from "./shared";

export function SaveEditor() {
  const savRef = useRef<DuneSave | null>(null);
  const [name, setName] = useState("");
  const [, setVer] = useState(0);
  const [sub, setSub] = useState<"globals" | "troops" | "sietches">("globals");
  const [troopSel, setTroopSel] = useState(0);
  const [sietchSel, setSietchSel] = useState(0);
  const [showAllTroops, setShowAllTroops] = useState(false);

  const sav = savRef.current;
  const edit = (fn: (s: DuneSave) => void) => {
    if (savRef.current) {
      fn(savRef.current);
      setVer((v) => v + 1);
    }
  };

  const load = (n: string, bytes: Uint8Array) => {
    try {
      savRef.current = new DuneSave(bytes);
      setName(n);
      setVer((v) => v + 1);
    } catch (e) {
      alert("Could not parse save: " + e);
    }
  };

  return (
    <div className="col">
      <LoadBar
        accept=".SAV,.sav"
        sampleName="SampleSave.SAV"
        hint="Load a Dune save file (DUNE*.SAV). Edits stay in your browser; export a new .SAV when done."
        onLoad={load}
      />

      {sav && (
        <>
          <div className="row">
            <div className="tabs grow" style={{ margin: 0, borderBottom: "none" }}>
              {(["globals", "troops", "sietches"] as const).map((t) => (
                <button key={t} className={"tab" + (sub === t ? " active" : "")} onClick={() => setSub(t)}>
                  {t.toUpperCase()}
                </button>
              ))}
            </div>
            <button className="btn primary" onClick={() => downloadBytes(name || "DUNE.SAV", sav.serialize())}>
              ⤓ Export .SAV
            </button>
          </div>

          {sub === "globals" && (
            <Panel title="Global state">
              <div className="row">
                <div className="field" style={{ minWidth: 220 }}>
                  <label>Game stage</label>
                  <select
                    value={sav.gameStage}
                    onChange={(e) => edit((s) => (s.gameStage = +e.target.value))}
                  >
                    {Object.entries(GAME_STAGES).map(([v, n]) => (
                      <option key={v} value={v}>
                        {hex(+v)} — {n}
                      </option>
                    ))}
                    {!(sav.gameStage in GAME_STAGES) && <option value={sav.gameStage}>{hex(sav.gameStage)} — (custom)</option>}
                  </select>
                </div>
                <NumberField label="Spice (×10 = kg)" value={sav.spice} max={65535} onChange={(v) => edit((s) => (s.spice = v))} style={{ width: 140 }} />
                <NumberField label="Charisma (÷2 shown)" value={sav.charisma} max={255} onChange={(v) => edit((s) => (s.charisma = v))} style={{ width: 140 }} />
                <NumberField label="Rallied troops" value={sav.ralliedTroops} max={255} onChange={(v) => edit((s) => (s.ralliedTroops = v))} style={{ width: 120 }} />
                <NumberField label="Day" value={sav.day} max={4095} onChange={(v) => edit((s) => s.setTime(v, undefined))} style={{ width: 100 }} />
                <NumberField label="Hour (0-15)" value={sav.hour} max={15} onChange={(v) => edit((s) => s.setTime(undefined, v))} style={{ width: 100 }} />
                <NumberField label="Contact dist" value={sav.contactDistance} max={255} onChange={(v) => edit((s) => (s.contactDistance = v))} style={{ width: 110 }} />
              </div>
              <div className="small muted" style={{ marginTop: 10 }}>
                Spice displayed in-game = value ×10 kg ({(sav.spice * 10).toLocaleString()} kg). Charisma shown in GUI = {Math.floor(sav.charisma / 2)}.
              </div>
            </Panel>
          )}

          {sub === "troops" && (
            <div className="row" style={{ alignItems: "flex-start" }}>
              <div className="grow">
                <Panel
                  title="Troops"
                  right={
                    <label className="small muted">
                      <input type="checkbox" checked={showAllTroops} onChange={(e) => setShowAllTroops(e.target.checked)} /> show all
                    </label>
                  }
                >
                  <div className="scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Job</th>
                          <th>Pop</th>
                          <th>Sietch</th>
                          <th>Equip</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sav.allTroops()
                          .filter((t) => showAllTroops || t.population > 0 || t.troop_id !== 0)
                          .map((t) => (
                            <tr key={t.index} className={"clickable" + (t.index === troopSel ? " sel" : "")} onClick={() => setTroopSel(t.index)}>
                              <td className="muted">{t.index}</td>
                              <td>{t.job_name}</td>
                              <td style={{ color: t.population ? "var(--amber)" : "var(--dim)" }}>{t.population || "-"}</td>
                              <td className="muted">{t.sietch_id}</td>
                              <td className="small muted">{t.equipment_str === "None" ? "-" : t.equipment_str}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </div>
              <div style={{ width: 300, flexShrink: 0 }}>
                {(() => {
                  const t = sav.troop(troopSel);
                  return (
                    <Panel title={`Edit troop #${troopSel}`} accent="var(--red)">
                      <div className="col">
                        <div className="field">
                          <label>Job</label>
                          <select value={t.job} onChange={(e) => edit((s) => s.setTroopField(troopSel, "job", +e.target.value))}>
                            {Object.entries(TROOP_JOBS).map(([v, n]) => (
                              <option key={v} value={v}>
                                {v} — {n}
                              </option>
                            ))}
                          </select>
                        </div>
                        <NumberField label="Population" value={t.population} max={65535} onChange={(v) => edit((s) => s.setTroopField(troopSel, "population", v))} />
                        <div className="row">
                          <NumberField label="Spice skill" value={t.spice_skill} max={255} onChange={(v) => edit((s) => s.setTroopField(troopSel, "spice_skill", v))} style={{ width: 88 }} />
                          <NumberField label="Army skill" value={t.army_skill} max={255} onChange={(v) => edit((s) => s.setTroopField(troopSel, "army_skill", v))} style={{ width: 88 }} />
                          <NumberField label="Eco skill" value={t.eco_skill} max={255} onChange={(v) => edit((s) => s.setTroopField(troopSel, "eco_skill", v))} style={{ width: 88 }} />
                        </div>
                        <div className="row">
                          <NumberField label="Motivation" value={t.motivation} max={255} onChange={(v) => edit((s) => s.setTroopField(troopSel, "motivation", v))} style={{ width: 110 }} />
                          <NumberField label="Dissatisf." value={t.dissatisfaction} max={255} onChange={(v) => edit((s) => s.setTroopField(troopSel, "dissatisfaction", v))} style={{ width: 110 }} />
                        </div>
                        <div className="field">
                          <label>Equipment ({hex(t.equipment)})</label>
                          <div className="row" style={{ gap: 4 }}>
                            {EQUIPMENT_FLAGS.map(([bit, label]) => (
                              <label key={bit} className="small" style={{ cursor: "pointer" }}>
                                <input
                                  type="checkbox"
                                  checked={!!(t.equipment & bit)}
                                  onChange={(e) =>
                                    edit((s) => s.setTroopField(troopSel, "equipment", e.target.checked ? t.equipment | bit : t.equipment & ~bit))
                                  }
                                />
                                {label}
                              </label>
                            ))}
                          </div>
                        </div>
                      </div>
                    </Panel>
                  );
                })()}
              </div>
            </div>
          )}

          {sub === "sietches" && (
            <div className="row" style={{ alignItems: "flex-start" }}>
              <div className="grow">
                <Panel title="Sietches / locations">
                  <div className="scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Name</th>
                          <th>Status</th>
                          <th>Spice</th>
                          <th>Dens</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sav.allSietches().map((s) => (
                          <tr key={s.index} className={"clickable" + (s.index === sietchSel ? " sel" : "")} onClick={() => setSietchSel(s.index)}>
                            <td className="muted">{s.index}</td>
                            <td>{s.name}</td>
                            <td className="small">
                              {s.discovered ? <Tag color="var(--amber)">D</Tag> : <Tag color="var(--dim)">?</Tag>}
                              {s.vegetation && <Tag color="var(--green)">V</Tag>}
                              {s.in_battle && <Tag color="var(--red)">B</Tag>}
                            </td>
                            <td className="muted">{s.spice_amount || "-"}</td>
                            <td className="muted">{s.spice_density || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </div>
              <div style={{ width: 300, flexShrink: 0 }}>
                {(() => {
                  const s = sav.sietch(sietchSel);
                  const setStatusBit = (bit: number, on: boolean) =>
                    edit((sv) => sv.setSietchField(sietchSel, "status", on ? s.status | bit : s.status & ~bit));
                  return (
                    <Panel title={`Edit #${sietchSel}: ${s.name}`} accent="var(--green)">
                      <div className="col">
                        <div className="field">
                          <label>Status flags ({hex(s.status)})</label>
                          <div className="col" style={{ gap: 2 }}>
                            {SIETCH_STATUS_FLAGS.map(([bit, label]) => (
                              <label key={bit} className="small" style={{ cursor: "pointer" }}>
                                <input type="checkbox" checked={!!(s.status & bit)} onChange={(e) => setStatusBit(bit, e.target.checked)} /> {label}
                              </label>
                            ))}
                          </div>
                        </div>
                        <div className="row">
                          <NumberField label="Spice amt" value={s.spice_amount} max={255} onChange={(v) => edit((sv) => sv.setSietchField(sietchSel, "spice_amount", v))} style={{ width: 100 }} />
                          <NumberField label="Density" value={s.spice_density} max={255} onChange={(v) => edit((sv) => sv.setSietchField(sietchSel, "spice_density", v))} style={{ width: 100 }} />
                          <NumberField label="Stage gate" value={s.stage_gate} max={255} hex onChange={(v) => edit((sv) => sv.setSietchField(sietchSel, "stage_gate", v))} style={{ width: 100 }} />
                        </div>
                        <div className="field">
                          <label>Equipment counts</label>
                          <div className="row">
                            <NumberField label="Harv" value={s.harvesters} max={255} onChange={(v) => edit((sv) => sv.setSietchField(sietchSel, "harvesters", v))} style={{ width: 70 }} />
                            <NumberField label="Orni" value={s.ornithopters} max={255} onChange={(v) => edit((sv) => sv.setSietchField(sietchSel, "ornithopters", v))} style={{ width: 70 }} />
                            <NumberField label="Atom" value={s.atomics} max={255} onChange={(v) => edit((sv) => sv.setSietchField(sietchSel, "atomics", v))} style={{ width: 70 }} />
                            <NumberField label="Gun" value={s.guns} max={255} onChange={(v) => edit((sv) => sv.setSietchField(sietchSel, "guns", v))} style={{ width: 70 }} />
                          </div>
                        </div>
                      </div>
                    </Panel>
                  );
                })()}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
