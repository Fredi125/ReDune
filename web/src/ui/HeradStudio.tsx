import { useMemo, useState } from "react";
import { loadHerad, parseTrackEvents, type HeradLoad } from "../codecs/herad";
import { downloadBytes, LoadBar, Panel, Tag } from "./shared";

const FMT_LABEL: Record<string, string> = { OPL2: "OPL2 / AdLib", AGD: "Tandy / PCjr", M32: "Roland MT-32" };

export function HeradStudio() {
  const [name, setName] = useState("");
  const [loaded, setLoaded] = useState<HeradLoad | null>(null);
  const [error, setError] = useState("");

  const load = (n: string, bytes: Uint8Array) => {
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
      const notes = ev.filter((e) => e.type === "NOTE_ON").length;
      return { index: t.index, size: t.size, events: ev.length, notes };
    });
  }, [loaded]);

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
            <button className="btn primary" onClick={() => downloadBytes(name.replace(/\.[^.]+$/, "") + ".mid", loaded.midi)}>
              ⤓ Export MIDI
            </button>
          }
        >
          <div className="row" style={{ gap: 16, marginBottom: 10 }}>
            <span className="small muted">
              <Tag color="var(--blue)">{loaded.info.tracks.length} tracks</Tag>
              <Tag color="var(--green)">{loaded.info.nInstruments} instruments</Tag>
              <Tag color="var(--amber)">{loaded.midi.length.toLocaleString()} B MIDI</Tag>
            </span>
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
            Exports a Standard MIDI File (format 1) playable in any MIDI player. The original used OPL2 FM / MT-32
            synthesis — faithful in-browser FM playback would need an OPL2 emulator (not bundled).
          </div>
        </Panel>
      )}
    </div>
  );
}
