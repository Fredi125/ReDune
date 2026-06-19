import { useEffect, useMemo, useRef, useState } from "react";
import { loadHerad, parseTrackEvents, type HeradInstrument, type HeradLoad } from "../codecs/herad";
import { midiToFreq, oplWaves, playFmNote } from "../audio/heradFm";
import { downloadBytes, LoadBar, Panel, Tag } from "./shared";
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
  const ctxRef = useRef<AudioContext | null>(null);
  const stopTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = (n: string, bytes: Uint8Array) => {
    stop();
    setError("");
    try {
      setLoaded(loadHerad(bytes, n));
      setName(n);
    } catch (e) {
      setLoaded(null);
      setError(String(e));
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
    const insts = loaded.instruments;
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
              <label className="muted">bpm</label>
              <input type="number" min={40} max={300} value={bpm} style={{ width: 56 }} onChange={(e) => setBpm(Math.max(40, +e.target.value || 120))} />
              <button className="btn primary" onClick={playing ? stop : play}>{playing ? "■ Stop" : "▶ Play"}</button>
              <button className="btn" onClick={() => downloadBytes(name.replace(/\.[^.]+$/, "") + ".mid", loaded.midi)}>⤓ MIDI</button>
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
          <div className="small muted" style={{ marginTop: 10 }}>
            <b>▶ Play</b> renders the decoded <b>OPL2 instrument patches</b> through a 2-operator WebAudio FM synth
            (real waveforms, MULT, TL, ADSR and FM/additive routing per patch) — close to the AdLib timbre, though not a
            cycle-exact YM3812 emulator. <b>⤓ MIDI</b> exports a Standard MIDI File for external players.
          </div>
        </Panel>
      )}
    </div>
  );
}
