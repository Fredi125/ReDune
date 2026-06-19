/** Shared UI primitives + helpers. */
import React, { useRef, useState } from "react";

export const hex = (v: number, w = 2) => "0x" + v.toString(16).toUpperCase().padStart(w, "0");

export function Panel(props: { title: string; accent?: string; right?: React.ReactNode; children: React.ReactNode }) {
  const accent = props.accent ?? "var(--amber)";
  return (
    <div className="panel">
      <div className="panel-h">
        <span className="dot" style={{ background: accent, boxShadow: `0 0 6px ${accent}66` }} />
        <span className="panel-title">{props.title}</span>
        <span className="grow" />
        {props.right}
      </div>
      <div className="panel-b">{props.children}</div>
    </div>
  );
}

export function Tag(props: { children: React.ReactNode; color?: string }) {
  const c = props.color ?? "var(--amber)";
  return (
    <span className="tag" style={{ color: c, borderColor: c + "55", background: c + "18" }}>
      {props.children}
    </span>
  );
}

export function Field(props: { label: string; children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div className="field" style={props.style}>
      <label>{props.label}</label>
      {props.children}
    </div>
  );
}

export function NumberField(props: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  hex?: boolean;
  style?: React.CSSProperties;
}) {
  return (
    <Field label={props.label} style={props.style}>
      <input
        type="number"
        value={props.value}
        min={props.min ?? 0}
        max={props.max ?? 65535}
        onChange={(e) => {
          let v = parseInt(e.target.value, 10);
          if (Number.isNaN(v)) v = 0;
          if (props.min !== undefined) v = Math.max(props.min, v);
          if (props.max !== undefined) v = Math.min(props.max, v);
          props.onChange(v);
        }}
      />
    </Field>
  );
}

/** Trigger a browser download of raw bytes. */
export function downloadBytes(filename: string, bytes: Uint8Array) {
  const ab = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(ab).set(bytes);
  const blob = new Blob([ab], { type: "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/**
 * Try to fetch a game file from the dev assets dir (web/public/game/<name>).
 * Returns null if not available (the primary path is user file upload).
 */
export async function fetchGame(name: string): Promise<Uint8Array | null> {
  try {
    const res = await fetch(`game/${name}`);
    if (!res.ok) return null;
    return new Uint8Array(await res.arrayBuffer());
  } catch {
    return null;
  }
}

/**
 * File loader bar: drag-and-drop + file picker, plus an optional
 * "load bundled sample" button that fetches from web/public/game/.
 */
export function LoadBar(props: {
  accept?: string;
  sampleName?: string;
  hint?: string;
  onLoad: (name: string, bytes: Uint8Array) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [status, setStatus] = useState<string>("");

  const handleFile = (f: File) => {
    const r = new FileReader();
    r.onload = () => {
      props.onLoad(f.name, new Uint8Array(r.result as ArrayBuffer));
      setStatus(`Loaded ${f.name} (${(r.result as ArrayBuffer).byteLength.toLocaleString()} B)`);
    };
    r.readAsArrayBuffer(f);
  };

  return (
    <div
      className={"dropzone" + (over ? " over" : "")}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
      }}
    >
      <button className="btn primary" onClick={() => inputRef.current?.click()}>
        Choose file…
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={props.accept}
        style={{ display: "none" }}
        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
      />
      {props.sampleName && (
        <button
          className="btn"
          onClick={async () => {
            setStatus("Fetching sample…");
            const b = await fetchGame(props.sampleName!);
            if (b) {
              props.onLoad(props.sampleName!, b);
              setStatus(`Loaded sample ${props.sampleName} (${b.length.toLocaleString()} B)`);
            } else {
              setStatus(`Sample not found — symlink your gamedata into web/public/game/`);
            }
          }}
        >
          Load {props.sampleName}
        </button>
      )}
      <span className="small muted grow">{status || props.hint || "Drag a file here, or choose one. Everything is decoded locally in your browser."}</span>
    </div>
  );
}
