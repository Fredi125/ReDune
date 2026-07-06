import { useEffect, useMemo, useRef, useState } from "react";
import { encodeHerad, loadHerad, OPL_MULT, parseTrackEvents, writeInstrument, type HeradInstrument, type HeradLoad } from "../codecs/herad";
import { hsqCompress } from "../codecs/compression";
import { midiToFreq, oplWaves, playFmNote, type FmTuning } from "../audio/heradFm";
import { OPL2, noteOff, noteOn, programChannel, renderHeradOpl2, DEFAULT_SYNTH_PARAMS, type SynthParams } from "../audio/opl2";
import { downloadBytes, hex, LoadBar, NumberField, Panel, Tag } from "./shared";
import { useIncoming } from "./routing";

const FMT_LABEL: Record<string, string> = { OPL2: "OPL2 / AdLib", AGD: "Tandy / PCjr", M32: "Roland MT-32" };
const TPQ = 120;
const MAX_VOICES = 6000;

// Fallback patch for files with no OPL instrument block (e.g. M32).
const DEFAULT_INST: HeradInstrument = {
  index: 0, mode: 0, feedback: 0, con: 1,
  modMul: 1, carMul: 1, modOut: 22, carOut: 0,
  modA: 11, modD: 6, modS: 4, modR: 6, carA: 13, carD: 7, carS: 2, carR: 6,
  modWave: 0, carWave: 0, modOutVel: 0, carOutVel: 1,
  modEgType: true, carEgType: true, modKsr: false, carKsr: false,
};

/** One labelled slider with a live value read-out. */
function Knob(props: { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; fmt?: (v: number) => string; title?: string; accent?: boolean; disabled?: boolean }) {
  return (
    <label className="knob" title={props.title} style={props.disabled ? { opacity: 0.4 } : undefined}>
      <span className="knob-l">{props.label}</span>
      <input type="range" min={props.min} max={props.max} step={props.step ?? 1} value={props.value} disabled={props.disabled} onChange={(e) => props.onChange(+e.target.value)} />
      <span className="knob-v" style={props.accent && !props.disabled ? { color: "var(--amber)" } : undefined}>{props.fmt ? props.fmt(props.value) : String(props.value)}</span>
    </label>
  );
}

const x1 = (v: number) => `${v > 0 ? "+" : ""}${v}`;
const pct = (v: number) => `${Math.round(v * 100)}%`;
const mul = (v: number) => `${v.toFixed(2)}×`;

// One-click starting points that bias the honest-but-tunable synth knobs.
const TUNE_PRESETS: { name: string; title: string; p: Partial<SynthParams> }[] = [
  { name: "Faithful", title: "Decoded defaults — carrier at written pitch, real EG-type", p: {} },
  { name: "Bright", title: "More FM depth + feedback: sharper, buzzier timbre", p: { fmDepth: 1.6, feedbackScale: 1.4 } },
  { name: "Mellow", title: "Less FM, longer envelopes: softer, rounder", p: { fmDepth: 0.6, envScale: 1.5 } },
  { name: "Hardware", title: "Literal chip behaviour: carrier MULT applied to pitch (voices leap octaves)", p: { carrierLiteral: true } },
  { name: "Organ", title: "Force sustaining envelopes — everything holds", p: { egMode: "sustain" } },
  { name: "Pluck", title: "Force percussive envelopes — everything decays", p: { egMode: "pluck" } },
];

export function HeradStudio() {
  const [name, setName] = useState("");
  const [loaded, setLoaded] = useState<HeradLoad | null>(null);
  const [error, setError] = useState("");
  const [bpm, setBpm] = useState(120);
  const [tune, setTune] = useState<SynthParams>(DEFAULT_SYNTH_PARAMS);
  const [playing, setPlaying] = useState(false);
  const [engine, setEngine] = useState<"opl2" | "webaudio">("opl2");
  const [rendering, setRendering] = useState(false);
  const ctxRef = useRef<AudioContext | null>(null);
  const stopTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const playRef = useRef<{ startCtxTime: number; fromSec: number } | null>(null);
  const genRef = useRef(0); // bumps on every stop/start so a superseded async render aborts
  const [insts, setInsts] = useState<HeradInstrument[]>([]);
  const [selInst, setSelInst] = useState(0);
  const [edited, setEdited] = useState(false);
  const setTuneField = <K extends keyof SynthParams>(k: K, v: SynthParams[K]) => setTune((t) => ({ ...t, [k]: v }));

  const load = (n: string, bytes: Uint8Array) => {
    stop();
    setError("");
    try {
      const l = loadHerad(bytes, n);
      setLoaded(l);
      setInsts(l.instruments.map((x) => ({ ...x })));
      setSelInst(0);
      setEdited(false);
      setName(n);
    } catch (e) {
      setLoaded(null);
      setError(String(e));
    }
  };

  const setInstField = (field: keyof HeradInstrument, value: number) => {
    setInsts((prev) => prev.map((ins, i) => (i === selInst ? { ...ins, [field]: value } : ins)));
    setEdited(true);
  };

  // Re-encode (byte-identical when unedited) with the edited instrument patches,
  // re-compressing to HSQ if the source was. This closes the music mod loop.
  const exportFile = () => {
    if (!loaded) return;
    let block: Uint8Array = loaded.data.slice(loaded.info.instOffset);
    insts.forEach((ins, i) => {
      block = writeInstrument(block, i, ins);
    });
    const rebuilt = encodeHerad(loaded.data, loaded.info, { instrumentBlock: block });
    const out = loaded.wasHsq ? hsqCompress(rebuilt) : rebuilt;
    downloadBytes(name || "music.hsq", out);
  };

  const previewInst = () => {
    const ins = insts[selInst];
    if (!ins) return;
    stop();
    const ctx = new AudioContext();
    ctxRef.current = ctx;
    const note = 60 + tune.transpose;
    if (engine === "opl2") {
      // Render a short note through the real OPL2 core and play the buffer.
      const opl = new OPL2(ctx.sampleRate);
      opl.fmDepth = tune.fmDepth;
      opl.envScale = tune.envScale;
      opl.feedbackScale = tune.feedbackScale;
      programChannel(opl, 0, ins, tune.egMode);
      const cm = tune.carrierLiteral ? 1 : OPL_MULT[ins.carMul] ?? 1;
      noteOn(opl, 0, note, cm);
      const n = Math.floor(ctx.sampleRate * 0.75);
      const arr = new Float32Array(n);
      const offAt = Math.floor(n * 0.6);
      for (let i = 0; i < n; i++) {
        if (i === offAt) noteOff(opl, 0, note, cm);
        arr[i] = opl.generate();
      }
      const buf = ctx.createBuffer(1, n, ctx.sampleRate);
      buf.getChannelData(0).set(arr);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const g = ctx.createGain();
      g.gain.value = 0.9;
      src.connect(g);
      g.connect(ctx.destination);
      src.start();
    } else {
      const master = ctx.createGain();
      master.gain.value = 0.5 * tune.gain;
      master.connect(ctx.destination);
      const t0 = ctx.currentTime + 0.05;
      const fmTune: FmTuning = { fmDepth: tune.fmDepth, carrierLiteral: tune.carrierLiteral, egMode: tune.egMode };
      playFmNote(ctx, master, oplWaves(ctx), ins, midiToFreq(note), 110, t0, t0 + 0.6, fmTune);
    }
    stopTimer.current = setTimeout(stop, 1100);
  };

  // Offline-render the whole song through the faithful OPL2 core and play it,
  // optionally starting `fromSec` in (so live re-tuning keeps your place).
  const startOpl2 = async (fromSec = 0) => {
    if (!loaded) return;
    stop();
    const gen = genRef.current;
    setRendering(true);
    await new Promise((r) => setTimeout(r, 10)); // let the "rendering…" state paint
    if (gen !== genRef.current) return; // superseded by a newer stop/start
    try {
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const insArr = insts.length ? insts : [DEFAULT_INST];
      const data = renderHeradOpl2(loaded.info.tracks, loaded.info.format, insArr, bpm, ctx.sampleRate, TPQ, 240, tune);
      setRendering(false);
      if (data.length === 0) {
        stop();
        return;
      }
      const dur = data.length / ctx.sampleRate;
      const off = Math.min(Math.max(0, fromSec), Math.max(0, dur - 0.05));
      const buf = ctx.createBuffer(1, data.length, ctx.sampleRate);
      buf.getChannelData(0).set(data);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const master = ctx.createGain();
      master.gain.value = 0.9;
      src.connect(master);
      master.connect(ctx.destination);
      src.start(0, off);
      playRef.current = { startCtxTime: ctx.currentTime, fromSec: off };
      setPlaying(true);
      stopTimer.current = setTimeout(stop, (dur - off + 0.3) * 1000);
    } catch (e) {
      setRendering(false);
      setError(String(e));
      stop();
    }
  };

  const trackStats = useMemo(() => {
    if (!loaded) return [];
    return loaded.info.tracks.map((t) => {
      const ev = parseTrackEvents(t.data, loaded.info.format);
      return { index: t.index, size: t.size, events: ev.length, notes: ev.filter((e) => e.type === "NOTE_ON" && e.data[1] > 0).length };
    });
  }, [loaded]);

  const stop = () => {
    genRef.current++; // invalidate any in-flight async render
    if (stopTimer.current) clearTimeout(stopTimer.current);
    stopTimer.current = null;
    if (ctxRef.current) {
      ctxRef.current.close().catch(() => {});
      ctxRef.current = null;
    }
    playRef.current = null;
    setRendering(false);
    setPlaying(false);
  };

  // Live WebAudio FM playback (schedules per note), from `fromSec` into the song.
  const startWeb = (fromSec = 0) => {
    if (!loaded) return;
    stop();
    const ctx = new AudioContext();
    ctxRef.current = ctx;
    const tick = 60 / bpm / TPQ; // seconds per tick
    const master = ctx.createGain();
    master.gain.value = 0.42 * tune.gain;
    master.connect(ctx.destination);
    const waves = oplWaves(ctx);
    const fmTune: FmTuning = { fmDepth: tune.fmDepth, carrierLiteral: tune.carrierLiteral, egMode: tune.egMode };
    const t0 = ctx.currentTime + 0.08;
    let voices = 0;
    let maxEnd = t0;

    for (const trk of loaded.info.tracks) {
      const events = parseTrackEvents(trk.data, loaded.info.format);
      let cur = 0;
      let prog = 0;
      const active = new Map<number, { instIdx: number; note: number; vel: number; start: number }>();
      const notes: { instIdx: number; note: number; vel: number; start: number; end: number }[] = [];
      for (const e of events) {
        cur += e.delta * tick;
        if (e.type === "PROG_CHG") prog = e.data[0];
        else if (e.type === "NOTE_ON" && e.data[1] > 0) {
          active.set(e.data[0], { instIdx: prog, note: e.data[0], vel: e.data[1], start: cur });
        } else if (e.type === "NOTE_OFF" || (e.type === "NOTE_ON" && e.data[1] === 0)) {
          const a = active.get(e.data[0]);
          if (a) {
            notes.push({ ...a, end: cur });
            active.delete(e.data[0]);
          }
        }
      }
      const tEnd = cur + 0.3;
      for (const [, a] of active) notes.push({ ...a, end: tEnd });
      for (const nt of notes) {
        if (nt.end < fromSec) continue; // already finished before our start point
        if (voices >= MAX_VOICES) break;
        const inst = insts[nt.instIdx] ?? insts[0] ?? DEFAULT_INST;
        const freq = midiToFreq(nt.note + tune.transpose);
        const st = t0 + Math.max(0, nt.start - fromSec);
        const en = t0 + Math.max(0, nt.end - fromSec);
        const end = playFmNote(ctx, master, waves, inst, freq, nt.vel, st, en, fmTune);
        maxEnd = Math.max(maxEnd, end);
        voices++;
      }
    }

    playRef.current = { startCtxTime: ctx.currentTime, fromSec };
    setPlaying(true);
    stopTimer.current = setTimeout(stop, Math.max(500, (maxEnd - ctx.currentTime + 0.3) * 1000));
  };

  const begin = (fromSec = 0) => (engine === "opl2" ? startOpl2(fromSec) : startWeb(fromSec));

  /** Song-seconds elapsed at the current instant (for position-preserving re-tune). */
  const currentPos = () => {
    const pr = playRef.current;
    const ctx = ctxRef.current;
    if (!pr || !ctx) return 0;
    return pr.fromSec + (ctx.currentTime - pr.startCtxTime);
  };

  useEffect(() => () => stop(), []);
  useIncoming("music", load);

  // Live re-tune: while playing, any tempo/tuning/patch change re-renders from the
  // current position after a short debounce — so you hear edits without losing your
  // place, and BPM (etc.) apply immediately instead of only on the next Play.
  useEffect(() => {
    if (!playing) return;
    const pos = currentPos();
    const id = setTimeout(() => begin(pos), 320);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bpm, tune, insts]);

  return (
    <div className="col">
      <LoadBar
        accept=".HSQ,.hsq,.AGD,.agd,.M32,.m32"
        sampleName="ARRAKIS.HSQ"
        hint="Load HERAD music: *.HSQ (OPL2/AdLib), *.AGD (Tandy), *.M32 (Roland MT-32)."
        onLoad={load}
      />
      {error && <div className="warn small">Not a HERAD music file: {error}</div>}

      {loaded && (
        <Panel
          title={`${name} — ${FMT_LABEL[loaded.info.format] ?? loaded.info.format}`}
          accent="var(--purple)"
          right={
            <div className="row small">
              <label className="muted">engine</label>
              <select value={engine} disabled={playing || rendering} title="OPL2 = faithful YM3812 software synth (feedback, real waveforms); WebAudio = lightweight FM approximation" onChange={(e) => setEngine(e.target.value as "opl2" | "webaudio")}>
                <option value="opl2">OPL2 (faithful)</option>
                <option value="webaudio">WebAudio FM</option>
              </select>
              <button className="btn primary" disabled={rendering} onClick={() => (playing ? stop() : begin(0))}>{rendering ? "⏳ rendering…" : playing ? "■ Stop" : "▶ Play"}</button>
              <button className="btn" onClick={() => downloadBytes(name.replace(/\.[^.]+$/, "") + ".mid", loaded.midi)}>⤓ MIDI</button>
              {edited && <Tag color="var(--amber)">edited</Tag>}
              <button className="btn primary" onClick={exportFile} title="Re-encode (byte-identical when unedited) and re-compress to HSQ">⤓ Export {loaded.wasHsq ? ".HSQ" : "file"}</button>
            </div>
          }
        >
          <div className="row" style={{ gap: 8, marginBottom: 10 }}>
            <Tag color="var(--blue)">{loaded.info.tracks.length} tracks</Tag>
            <Tag color="var(--green)">{loaded.instruments.length} FM patches</Tag>
            <Tag color="var(--amber)">{loaded.midi.length.toLocaleString()} B MIDI</Tag>
          </div>

          <div className="tune-panel">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 8, alignItems: "baseline" }}>
              <b className="small">🎛 Live tuning{playing ? <span className="muted" style={{ fontWeight: 400 }}> · drag to hear changes in place</span> : <span className="muted" style={{ fontWeight: 400 }}> · press ▶ Play, then tweak</span>}</b>
              <div className="row small" style={{ gap: 4 }}>
                {TUNE_PRESETS.map((p) => (
                  <button key={p.name} className="btn small" title={p.title} onClick={() => setTune({ ...DEFAULT_SYNTH_PARAMS, ...p.p })}>{p.name}</button>
                ))}
                <button className="btn small" title="Restore decoded defaults + 120 bpm" onClick={() => { setTune(DEFAULT_SYNTH_PARAMS); setBpm(120); }}>↺ reset</button>
              </div>
            </div>
            <div className="tune-grid">
              <Knob label="tempo" value={bpm} min={40} max={300} onChange={setBpm} fmt={(v) => `${v} bpm`} accent title="Playback tempo. HERAD files carry no absolute tempo, so 120 is a starting guess — tune to taste." />
              <Knob label="transpose" value={tune.transpose} min={-24} max={24} onChange={(v) => setTuneField("transpose", v)} fmt={x1} title="Shift every note by semitones (±2 octaves)." />
              <Knob label="volume" value={tune.gain} min={0} max={1.5} step={0.05} onChange={(v) => setTuneField("gain", v)} fmt={pct} title="Master output level." />
              <Knob label="FM depth" value={tune.fmDepth} min={0} max={3} step={0.05} onChange={(v) => setTuneField("fmDepth", v)} fmt={mul} title="FM modulation index — higher = brighter/buzzier, lower = purer/cleaner." />
              <Knob label="envelope" value={tune.envScale} min={0.25} max={3} step={0.05} onChange={(v) => setTuneField("envScale", v)} fmt={mul} disabled={engine === "webaudio"} title="Envelope time scale — higher = slower attacks & longer decays. (OPL2 engine)" />
              <Knob label="feedback" value={tune.feedbackScale} min={0} max={2} step={0.05} onChange={(v) => setTuneField("feedbackScale", v)} fmt={mul} disabled={engine === "webaudio"} title="Modulator self-feedback scale — adds grit/edge. (OPL2 engine)" />
            </div>
            <div className="row small" style={{ gap: 14, marginTop: 8 }}>
              <label className="muted" title="Carrier at the written pitch (recommended, in-tune) vs. literal chip behaviour where the carrier MULT multiplies pitch — authentic but many voices leap octaves.">
                carrier pitch{" "}
                <select value={tune.carrierLiteral ? "literal" : "musical"} onChange={(e) => setTuneField("carrierLiteral", e.target.value === "literal")}>
                  <option value="musical">musical (in-tune)</option>
                  <option value="literal">hardware (raw MULT)</option>
                </select>
              </label>
              <label className="muted" title="Envelope type: 'faithful' uses each patch's decoded bit; or force every voice to sustain (hold) or pluck (decay).">
                envelope type{" "}
                <select value={tune.egMode} onChange={(e) => setTuneField("egMode", e.target.value as SynthParams["egMode"])}>
                  <option value="faithful">faithful (per-patch)</option>
                  <option value="sustain">force sustain</option>
                  <option value="pluck">force pluck</option>
                </select>
              </label>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Track</th>
                <th>Bytes</th>
                <th>Events</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {trackStats.map((t) => (
                <tr key={t.index}>
                  <td className="muted">{t.index}</td>
                  <td className="muted small">{t.size}</td>
                  <td className="small">{t.events}</td>
                  <td className="small" style={{ color: "var(--amber)" }}>{t.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {insts.length > 0 && (
            <div style={{ marginTop: 12, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
              <div className="row small" style={{ marginBottom: 8 }}>
                <b>FM instrument editor</b>
                <label className="muted">patch</label>
                <select value={selInst} onChange={(e) => setSelInst(+e.target.value)}>
                  {insts.map((_, i) => (<option key={i} value={i}>#{i}</option>))}
                </select>
                <button className="btn small" onClick={previewInst}>♪ test note</button>
                <span className="muted small">edits feed ▶ Play and ⤓ Export</span>
              </div>
              {insts[selInst] && (
                <div className="row" style={{ gap: 16, flexWrap: "wrap" }}>
                  <div>
                    <div className="small muted">routing</div>
                    <NumberField label="feedback (0-7)" value={insts[selInst].feedback} max={7} onChange={(v) => setInstField("feedback", v)} />
                    <NumberField label="con (FM>0/add)" value={insts[selInst].con} max={127} onChange={(v) => setInstField("con", v)} />
                  </div>
                  <div>
                    <div className="small muted">modulator</div>
                    <NumberField label="mult (0-15)" value={insts[selInst].modMul} max={15} onChange={(v) => setInstField("modMul", v)} />
                    <NumberField label="level (0-63)" value={insts[selInst].modOut} max={63} onChange={(v) => setInstField("modOut", v)} />
                    <NumberField label="wave (0-3)" value={insts[selInst].modWave} max={3} onChange={(v) => setInstField("modWave", v)} />
                    <NumberField label="A/D/S/R" value={insts[selInst].modA} max={15} onChange={(v) => setInstField("modA", v)} />
                  </div>
                  <div>
                    <div className="small muted">carrier</div>
                    <NumberField label="mult (0-15)" value={insts[selInst].carMul} max={15} onChange={(v) => setInstField("carMul", v)} />
                    <NumberField label="level (0-63)" value={insts[selInst].carOut} max={63} onChange={(v) => setInstField("carOut", v)} />
                    <NumberField label="wave (0-3)" value={insts[selInst].carWave} max={3} onChange={(v) => setInstField("carWave", v)} />
                    <NumberField label="A/D/S/R" value={insts[selInst].carA} max={15} onChange={(v) => setInstField("carA", v)} />
                  </div>
                </div>
              )}
              <div className="small muted" style={{ marginTop: 6 }}>
                Patch #{selInst} writes back to the 40-byte record at {hex(loaded.info.instOffset + selInst * 40)}; unedited
                fields and unknown bytes are preserved (byte-identical round-trip verified).
              </div>
            </div>
          )}
          <div className="small muted" style={{ marginTop: 10 }}>
            <b>🎛 Live tuning</b> lets you dial the song in yourself — while it plays, dragging any slider re-renders from the
            current spot, so you hear the change without losing your place (tempo, transpose &amp; volume work on both engines;
            envelope &amp; feedback are OPL2-only). The <b>carrier pitch</b> and <b>envelope type</b> selectors let you A/B our
            two interpretive calls: carrier-at-written-pitch vs. the literal chip MULT, and per-patch vs. forced envelopes.
            Presets are just starting points. <b>▶ Play</b> drives the decoded <b>OPL2 instrument patches</b>: <b>OPL2 (faithful)</b>{" "}
            is a sample-accurate YM3812 software synth (real register writes from the <code>DNADL</code> disasm, modulator
            self-feedback, the four OPL2 waveforms, FM/additive routing, per-operator ADSR); <b>WebAudio FM</b> is the older
            lightweight approximation. <b>⤓ MIDI</b> exports a Standard MIDI File. Edits to the FM patches below also feed
            playback live.
          </div>
        </Panel>
      )}
    </div>
  );
}
