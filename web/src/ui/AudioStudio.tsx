import { useEffect, useRef, useState } from "react";
import { decodeVoc, encodeVoc, encodeVocHsq, vocToWav, wavToSamples, type VocResult } from "../codecs/voc";
import { downloadBytes, LoadBar, Panel } from "./shared";

function Waveform({ v }: { v: VocResult }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const W = (c.width = 600);
    const H = (c.height = 90);
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#0d0b08";
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = "#7ec8e3";
    ctx.beginPath();
    const n = v.samples.length;
    const step = Math.max(1, Math.floor(n / W));
    for (let x = 0; x < W; x++) {
      let min = 255;
      let max = 0;
      for (let i = x * step; i < (x + 1) * step && i < n; i++) {
        if (v.samples[i] < min) min = v.samples[i];
        if (v.samples[i] > max) max = v.samples[i];
      }
      const y1 = H - (min / 255) * H;
      const y2 = H - (max / 255) * H;
      ctx.moveTo(x, y1);
      ctx.lineTo(x, y2);
    }
    ctx.stroke();
  }, [v]);
  return <canvas ref={ref} style={{ width: "100%", maxWidth: 600, border: "1px solid var(--border)", borderRadius: 4 }} />;
}

export function AudioStudio() {
  const [name, setName] = useState("");
  const [voc, setVoc] = useState<VocResult | null>(null);
  const [error, setError] = useState("");
  const [loop, setLoop] = useState(false);
  const [playing, setPlaying] = useState(false);
  const ctxRef = useRef<AudioContext | null>(null);
  const srcRef = useRef<AudioBufferSourceNode | null>(null);

  const wavInput = useRef<HTMLInputElement>(null);

  const importWav = (file: File) => {
    stop();
    setError("");
    const r = new FileReader();
    r.onload = () => {
      try {
        const { samples, sampleRate } = wavToSamples(new Uint8Array(r.result as ArrayBuffer));
        setVoc({ samples, sampleRate, duration: sampleRate > 0 ? samples.length / sampleRate : 0, soundBlocks: 1 });
        setName(file.name.replace(/\.[^.]+$/, ""));
      } catch (e) {
        setError("WAV import failed: " + e);
      }
    };
    r.readAsArrayBuffer(file);
  };

  const load = (n: string, bytes: Uint8Array) => {
    stop();
    setError("");
    try {
      setVoc(decodeVoc(bytes));
      setName(n.replace(/\.[^.]+$/, ""));
    } catch (e) {
      setVoc(null);
      setError(String(e));
    }
  };

  const stop = () => {
    try {
      srcRef.current?.stop();
    } catch {
      /* already stopped */
    }
    srcRef.current = null;
    setPlaying(false);
  };

  const play = () => {
    if (!voc) return;
    stop();
    const ctx = ctxRef.current ?? (ctxRef.current = new AudioContext());
    const sr = voc.sampleRate || 8000;
    const buf = ctx.createBuffer(1, voc.samples.length, sr);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < voc.samples.length; i++) ch[i] = (voc.samples[i] - 128) / 128;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = loop;
    src.connect(ctx.destination);
    src.onended = () => {
      if (srcRef.current === src) {
        srcRef.current = null;
        setPlaying(false);
      }
    };
    src.start();
    srcRef.current = src;
    setPlaying(true);
  };

  useEffect(() => () => stop(), []);

  return (
    <div className="col">
      <LoadBar
        accept=".HSQ,.hsq,.VOC,.voc"
        sampleName="SN1.HSQ"
        hint="Load a sound effect: SN1-SN9 / SNA (.HSQ or .VOC). Decoded and played in your browser."
        onLoad={load}
      />
      {error && <div className="warn small">Not a VOC sound file: {error}</div>}

      {voc && (
        <Panel
          title={`${name} — ${voc.sampleRate.toLocaleString()} Hz · ${voc.duration.toFixed(2)}s · ${voc.samples.length.toLocaleString()} samples`}
          accent="var(--blue)"
          right={
            <div className="row small">
              <label className="muted">
                <input type="checkbox" checked={loop} onChange={(e) => setLoop(e.target.checked)} /> loop
              </label>
              <button className="btn primary" onClick={playing ? stop : play}>
                {playing ? "■ Stop" : "▶ Play"}
              </button>
              <button className="btn" onClick={() => wavInput.current?.click()}>
                ↑ Replace from WAV
              </button>
              <input ref={wavInput} type="file" accept=".wav,audio/wav" style={{ display: "none" }} onChange={(e) => e.target.files?.[0] && importWav(e.target.files[0])} />
              <button className="btn" onClick={() => downloadBytes(`${name}.VOC`, encodeVoc(voc.samples, voc.sampleRate))}>
                ⤓ VOC
              </button>
              <button className="btn" onClick={() => downloadBytes(`${name}.HSQ`, encodeVocHsq(voc.samples, voc.sampleRate))}>
                ⤓ HSQ
              </button>
              <button className="btn" onClick={() => downloadBytes(`${name}.wav`, vocToWav(voc))}>
                ⤓ WAV
              </button>
            </div>
          }
        >
          <Waveform v={voc} />
          <div className="small muted" style={{ marginTop: 8 }}>
            8-bit PCM, mono. The original game loops several of these (worm/wind/harvester); toggle <b>loop</b> to hear it.
          </div>
        </Panel>
      )}
    </div>
  );
}
