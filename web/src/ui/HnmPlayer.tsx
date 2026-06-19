import { useEffect, useRef, useState } from "react";
import { framebufToRGBA, HnmFile } from "../codecs/hnm";
import { vocToWav } from "../codecs/voc";
import { downloadBytes, LoadBar, Panel } from "./shared";

export function HnmPlayer() {
  const fileRef = useRef<HnmFile | null>(null);
  const fbRef = useRef<Uint8Array>(new Uint8Array(64000));
  const palRef = useRef<Uint8Array>(new Uint8Array(768));
  const curRef = useRef<number>(-1); // last decoded frame index
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const audioSrc = useRef<AudioBufferSourceNode | null>(null);

  const [name, setName] = useState("");
  const [frame, setFrame] = useState(0);
  const [count, setCount] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [fps, setFps] = useState(12);
  const [scale, setScale] = useState(2);
  const [error, setError] = useState("");

  const render = () => {
    const c = canvasRef.current;
    if (!c) return;
    c.width = 320;
    c.height = 200;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const id = ctx.createImageData(320, 200);
    id.data.set(framebufToRGBA(fbRef.current, palRef.current));
    ctx.putImageData(id, 0, 0);
  };

  const decodeTo = (target: number) => {
    const h = fileRef.current;
    if (!h) return;
    if (target < curRef.current) {
      fbRef.current = new Uint8Array(64000);
      palRef.current = h.palette.slice();
      curRef.current = -1;
    }
    while (curRef.current < target) {
      curRef.current++;
      h.decodeFrame(curRef.current, fbRef.current, palRef.current);
    }
    render();
  };

  const load = (n: string, bytes: Uint8Array) => {
    stopAudio();
    setPlaying(false);
    setError("");
    try {
      const h = new HnmFile(bytes);
      fileRef.current = h;
      fbRef.current = new Uint8Array(64000);
      palRef.current = h.palette.slice();
      curRef.current = -1;
      setName(n.replace(/\.[^.]+$/, ""));
      setCount(h.frameCount);
      setFrame(0);
      decodeTo(0);
    } catch (e) {
      fileRef.current = null;
      setCount(0);
      setError(String(e));
    }
  };

  // playback loop
  useEffect(() => {
    if (!playing || !fileRef.current) return;
    const id = setInterval(() => {
      const next = curRef.current + 1;
      if (next >= count) {
        setPlaying(false);
        return;
      }
      decodeTo(next);
      setFrame(next);
    }, Math.max(20, 1000 / fps));
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, fps, count]);

  const seek = (i: number) => {
    decodeTo(i);
    setFrame(i);
  };

  const stopAudio = () => {
    try {
      audioSrc.current?.stop();
    } catch {
      /* ignore */
    }
    audioSrc.current = null;
  };

  const playAudio = () => {
    const h = fileRef.current;
    if (!h) return;
    stopAudio();
    const samples = h.extractSound();
    if (samples.length === 0) return;
    const ctx = audioCtx.current ?? (audioCtx.current = new AudioContext());
    const sr = 11111;
    const buf = ctx.createBuffer(1, samples.length, sr);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < samples.length; i++) ch[i] = (samples[i] - 128) / 128;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start();
    audioSrc.current = src;
  };

  useEffect(() => () => stopAudio(), []);

  const hasSound = fileRef.current ? fileRef.current.extractSound().length > 0 : false;

  return (
    <div className="col">
      <LoadBar accept=".HNM,.hnm" sampleName="CRYO2.HNM" hint="Load an HNM cutscene (e.g. CRYO2, FORT, DEAD3). Decoded and played in your browser." onLoad={load} />
      {error && <div className="warn small">Not an HNM video: {error}</div>}

      {fileRef.current && (
        <Panel
          title={`${name} — ${count} frames`}
          accent="var(--blue)"
          right={
            <div className="row small">
              <label className="muted">fps</label>
              <input type="number" min={1} max={30} value={fps} style={{ width: 50 }} onChange={(e) => setFps(Math.max(1, +e.target.value || 12))} />
              <label className="muted">scale</label>
              <input type="range" min={1} max={3} value={scale} onChange={(e) => setScale(+e.target.value)} />
            </div>
          }
        >
          <canvas ref={canvasRef} className="pixel" style={{ width: 320 * scale, height: 200 * scale, border: "1px solid var(--border)", display: "block" }} />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn primary" onClick={() => setPlaying((p) => !p)}>
              {playing ? "■ Pause" : "▶ Play"}
            </button>
            <button className="btn" onClick={() => seek(0)}>
              ⏮ Restart
            </button>
            <button className="btn" disabled={frame <= 0} onClick={() => seek(frame - 1)}>
              ◀ Prev
            </button>
            <button className="btn" disabled={frame >= count - 1} onClick={() => seek(frame + 1)}>
              Next ▶
            </button>
            <input type="range" className="grow" min={0} max={Math.max(0, count - 1)} value={frame} onChange={(e) => { setPlaying(false); seek(+e.target.value); }} />
            <span className="small muted" style={{ width: 70, textAlign: "right" }}>
              {frame + 1}/{count}
            </span>
          </div>
          {hasSound && (
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn" onClick={playAudio}>
                ♪ Play audio track
              </button>
              <button className="btn" onClick={() => downloadBytes(`${name}.wav`, vocToWav({ sampleRate: 11111, samples: fileRef.current!.extractSound(), duration: 0, soundBlocks: 0 }))}>
                ⤓ WAV
              </button>
              <span className="small muted">audio is the full soundtrack (A/V sync is approximate)</span>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
