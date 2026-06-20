import { useEffect, useMemo, useRef, useState } from "react";
import { encodeHerad, loadHerad, parseTrackEvents, writeInstrument, type HeradInstrument, type HeradLoad } from "../codecs/herad";
import { hsqCompress } from "../codecs/compression";
import { midiToFreq, oplWaves, playFmNote } from "../audio/heradFm";
import { OPL2, noteOff, noteOn, programChannel, renderHeradOpl2 } from "../audio/opl2";
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
};

export function HeradStudio() {
  const [name, setName] = useState("");
  const [loaded, setLoaded] = useState<HeradLoad | null>(null);
  const [error, setError] = useState("");
  const [bpm, setBpm] = useState(120);
  const [playing, setPlaying] = useState(false);
  const [engine, setEngine] = useState<"opl2" | "webaudio">("opl2");
  const [rendering, setRendering] = useState(false);
  const ctxRef = useRef<AudioContext | null>(null);
  const stopTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [insts, setInsts] = useState<HeradInstrument[]>([]);
  const [selInst, setSelInst] = useState(0);
  const [edited, setEdited] = useState(false);

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
    if (engine === "opl2") {
      // Render a short note through the real OPL2 core and play the buffer.
      const opl = new OPL2(ctx.sampleRate);
      programChannel(opl, 0, ins);
      noteOn(opl, 0, 60);
      const n = Math.floor(ctx.sampleRate * 0.75);
      const arr = new Float32Array(n);
      const offAt = Math.floor(n * 0.6);
      for (let i = 0; i < n; i++) {
        if (i === offAt) noteOff(opl, 0, 60);
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
      master.gain.value = 0.5;
      master.connect(ctx.destination);
      const t0 = ctx.currentTime + 0.05;
      playFmNote(ctx, master, oplWaves(ctx), ins, midiToFreq(60), 110, t0, t0 + 0.6);
    }
    stopTimer.current = setTimeout(stop, 1100);
  };

  // Offline-render the whole song through the faithful OPL2 core and play it.
  const playOpl2 = async () => {
    if (!loaded) return;
    stop();
    setRendering(true);
    await new Promise((r) => setTimeout(r, 10)); // let the "rendering…" state paint
    try {
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const insArr = insts.length ? insts : [DEFAULT_INST];
      const data = renderHeradOpl2(loaded.info.tracks, loaded.info.format, insArr, bpm, ctx.sampleRate, TPQ);
      setRendering(false);
      if (data.length === 0) {
        stop();
        return;
      }
      const buf = ctx.createBuffer(1, data.length, ctx.sampleRate);
      buf.getChannelData(0).set(data);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const master = ctx.createGain();
      master.gain.value = 0.9;
      src.connect(master);
      master.connect(ctx.destination);
      src.start();
      setPlaying(true);
      stopTimer.current = setTimeout(stop, (data.length / ctx.sampleRate + 0.3) * 1000);
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
    if (stopTimer.current) clearTimeout(stopTimer.current);
    stopTimer.current = null;
    if (ctxRef.current) {
      ctxRef.current.close().catch(() => {});
      ctxRef.current = null;
    }
    setPlaying(false);
  };

  const play = () => {
    if (!loaded) return;
    stop();
    const ctx = new AudioContext();
    ctxRef.current = ctx;
    const tick = 60 / bpm / TPQ; // seconds per tick
    const master = ctx.createGain();
    master.gain.value = 0.42;
    master.connect(ctx.destination);
    const waves = oplWaves(ctx);
    const t0 = ctx.currentTime + 0.08;
    let voices = 0;
    let maxEnd = t0;

    for (const trk of loaded.info.tracks) {
      const events = parseTrackEvents(trk.data, loaded.info.format);
      let cur = 0;
      let prog = 0;
      const active = new Map<number, { instIdx: number; freq: number; vel: number; t0: number }>();
      const notes: { instIdx: number; freq: number; vel: number; t0: number; t1: number }[] = [];
      for (const e of events) {
        cur += e.delta * tick;
        if (e.type === "PROG_CHG") prog = e.data[0];
        else if (e.type === "NOTE_ON" && e.data[1] > 0) {
          active.set(e.data[0], { instIdx: prog, freq: midiToFreq(e.data[0]), vel: e.data[1], t0: t0 + cur });
        } else if (e.type === "NOTE_OFF" || (e.type === "NOTE_ON" && e.data[1] === 0)) {
          const a = active.get(e.data[0]);
          if (a) {
            notes.push({ ...a, t1: t0 + cur });
            active.delete(e.data[0]);
          }
        }
      }
      const tEnd = t0 + cur + 0.3;
      for (const [, a] of active) notes.push({ ...a, t1: tEnd });
      for (const nt of notes) {
        if (voices >= MAX_VOICES) break;
        const inst = insts[nt.instIdx] ?? insts[0] ?? DEFAULT_INST;
        const end = playFmNote(ctx, master, waves, inst, nt.freq, nt.vel, nt.t0, nt.t1);
        maxEnd = Math.max(maxEnd, end);
        voices++;
      }
    }

    setPlaying(true);
    stopTimer.current = setTimeout(stop, Math.max(500, (maxEnd - ctx.currentTime + 0.3) * 1000));
  };

  useEffect(() => () => stop(), []);
  useIncoming("music", load);

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
              <label className="muted">bpm</label>
              <input type="number" min={40} max={300} value={bpm} style={{ width: 56 }} onChange={(e) => setBpm(Math.max(40, +e.target.value || 120))} />
              <button className="btn primary" disabled={rendering} onClick={playing ? stop : engine === "opl2" ? playOpl2 : play}>{rendering ? "⏳ rendering…" : playing ? "■ Stop" : "▶ Play"}</button>
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
            <b>▶ Play</b> drives the decoded <b>OPL2 instrument patches</b> through the selected engine. <b>OPL2 (faithful)</b>{" "}
            is a sample-accurate YM3812 software synth — programmed via real register writes (slot tables + F-number table from
            the <code>DNADL</code> driver disasm), with modulator self-<b>feedback</b>, the four OPL2 waveforms via the real
            log-sin/exp pipeline, FM/additive routing and per-operator ADSR; it offline-renders the song to a buffer
            (KSL/vibrato and cycle-exact EG timing are the remaining approximations). <b>WebAudio FM</b> is the older
            lightweight oscillator approximation. <b>⤓ MIDI</b> exports a Standard MIDI File for external players.
          </div>
        </Panel>
      )}
    </div>
  );
}
