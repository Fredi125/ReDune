import { useEffect, useMemo, useRef, useState } from "react";
import { loadHerad, parseTrackEvents, type HeradLoad } from "../codecs/herad";
import { downloadBytes, LoadBar, Panel, Tag } from "./shared";

const FMT_LABEL: Record<string, string> = { OPL2: "OPL2 / AdLib", AGD: "Tandy / PCjr", M32: "Roland MT-32" };
const TPQ = 120;
const MAX_VOICES = 6000;

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
    master.gain.value = 0.16;
    master.connect(ctx.destination);
    const t0 = ctx.currentTime + 0.06;
    let voices = 0;
    let maxEnd = t0;

    for (const trk of loaded.info.tracks) {
      const events = parseTrackEvents(trk.data, loaded.info.format);
      let cur = 0;
      const active = new Map<number, { osc: OscillatorNode; g: GainNode }>();
      for (const e of events) {
        cur += e.delta * tick;
        const t = t0 + cur;
        if (e.type === "NOTE_ON" && e.data[1] > 0) {
          if (voices >= MAX_VOICES) break;
          const note = e.data[0];
          const prev = active.get(note);
          if (prev) {
            prev.g.gain.setTargetAtTime(0, t, 0.01);
            prev.osc.stop(t + 0.05);
          }
          const osc = ctx.createOscillator();
          osc.type = "square";
          osc.frequency.value = 440 * Math.pow(2, (note - 69) / 12);
          const g = ctx.createGain();
          const vol = Math.min(0.5, (e.data[1] / 127) * 0.5);
          g.gain.setValueAtTime(0, t);
          g.gain.linearRampToValueAtTime(vol, t + 0.008);
          osc.connect(g);
          g.connect(master);
          osc.start(t);
          active.set(note, { osc, g });
          voices++;
        } else if (e.type === "NOTE_OFF" || (e.type === "NOTE_ON" && e.data[1] === 0)) {
          const v = active.get(e.data[0]);
          if (v) {
            v.g.gain.setTargetAtTime(0, t, 0.03);
            v.osc.stop(t + 0.15);
            active.delete(e.data[0]);
            maxEnd = Math.max(maxEnd, t + 0.15);
          }
        }
      }
      const tEnd = t0 + cur + 0.2;
      for (const [, v] of active) {
        v.g.gain.setTargetAtTime(0, tEnd, 0.05);
        v.osc.stop(tEnd + 0.2);
      }
      maxEnd = Math.max(maxEnd, tEnd + 0.2);
    }

    setPlaying(true);
    stopTimer.current = setTimeout(stop, Math.max(500, (maxEnd - ctx.currentTime + 0.3) * 1000));
  };

  useEffect(() => () => stop(), []);

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
            <Tag color="var(--green)">{loaded.info.nInstruments} instruments</Tag>
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
            <b>▶ Play</b> uses a lightweight WebAudio synth on the decoded note events — you hear the actual composition,
            but it's <i>not</i> authentic FM/MT-32 timbre. For true sound, <b>⤓ MIDI</b> exports a Standard MIDI File
            (faithful FM playback would need an OPL2 emulator + the still-undecoded instrument-patch format).
          </div>
        </Panel>
      )}
    </div>
  );
}
