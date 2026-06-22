import { useRef, useState, type ReactNode } from "react";
import { SpriteViewer } from "./ui/SpriteViewer";
import { SaveEditor } from "./ui/SaveEditor";
import { ConditStudio } from "./ui/ConditStudio";
import { RoomStudio } from "./ui/RoomStudio";
import { TextStudio } from "./ui/TextStudio";
import { MapViewer } from "./ui/MapViewer";
import { AudioStudio } from "./ui/AudioStudio";
import { StoryStudio } from "./ui/StoryStudio";
import { PlayRuntime } from "./ui/PlayRuntime";
import { FontViewer } from "./ui/FontViewer";
import { DatStudio } from "./ui/DatStudio";
import { HnmPlayer } from "./ui/HnmPlayer";
import { HeradStudio } from "./ui/HeradStudio";
import { ErrorBoundary, Panel } from "./ui/shared";
import { RoutedProvider, type IncomingFile } from "./ui/routing";
import { detectAssetType, TAB_LABELS } from "./ui/detect";

type Tab = "sprites" | "rooms" | "map" | "font" | "text" | "audio" | "music" | "video" | "story" | "play" | "save" | "condit" | "archive" | "about";

const TABS: { id: Tab; label: string }[] = [
  { id: "sprites", label: "◳ Sprites" },
  { id: "rooms", label: "▦ Rooms" },
  { id: "map", label: "🌍 Map" },
  { id: "font", label: "Aa Font" },
  { id: "text", label: "✎ Text" },
  { id: "audio", label: "♪ Audio" },
  { id: "music", label: "♫ Music" },
  { id: "video", label: "▶ Video" },
  { id: "story", label: "✦ Story" },
  { id: "play", label: "▷ Play" },
  { id: "save", label: "⚔ Save editor" },
  { id: "condit", label: "⎔ CONDIT studio" },
  { id: "archive", label: "🗜 Archive" },
  { id: "about", label: "ⓘ About" },
];

const FEATURES: { ico: string; name: string; desc: ReactNode }[] = [
  { ico: "◳", name: "Sprites", desc: <>Decode any sprite <code>.HSQ</code> to canvas, export PNG, swap frames with your own art and re-export a working sheet.</> },
  { ico: "▦", name: "Rooms", desc: <>Composite <code>.SAL</code> rooms — gradient walls + furniture tiles — edit placements, export a byte-perfect <code>.SAL</code>.</> },
  { ico: "🌍", name: "Map", desc: <>Paint <code>MAP.HSQ</code> terrain, or spin Arrakis as a globe wrapped with the real world map.</> },
  { ico: "Aa", name: "Font", desc: <>Pixel-edit the <code>DNCHAR.BIN</code> bitmap font with a live text preview; re-export byte-identical.</> },
  { ico: "✎", name: "Text", desc: <>Translate or mod <code>PHRASE</code> dialogue &amp; <code>COMMAND</code> UI strings, re-export a working <code>.HSQ</code>.</> },
  { ico: "♪", name: "Audio", desc: <>Play <code>VOC</code> sound effects, import a WAV, and re-export a working <code>.VOC</code> / <code>.HSQ</code>.</> },
  { ico: "♫", name: "Music", desc: <>Play HERAD songs through a faithful <b>OPL2</b> FM synth, tweak instrument patches, export MIDI.</> },
  { ico: "▶", name: "Video", desc: <>Decode &amp; play <code>.HNM</code> cutscenes on canvas with their soundtrack; export frames + WAV.</> },
  { ico: "✦", name: "Story", desc: <>Cross-reference DIALOGUE × CONDIT × PHRASE — every line with its gating condition and text.</> },
  { ico: "▷", name: "Play", desc: <>The live runtime: the real CONDIT VM unlocks dialogue as you edit <b>GameStage</b> &amp; flags.</> },
  { ico: "⚔", name: "Save editor", desc: <>Edit <code>DUNE*.SAV</code> globals, troops, sietches, NPCs &amp; smugglers; export a working save.</> },
  { ico: "⎔", name: "CONDIT studio", desc: <>Browse, decompile &amp; recompile all <b>713</b> condition entries; patch and re-export <code>CONDIT.HSQ</code>.</> },
  { ico: "🗜", name: "Archive", desc: <>Open <code>DUNE.DAT</code>, extract/replace any file, rebuild the archive — the full mod loop.</> },
];

function About() {
  return (
    <div className="col">
      <div className="about-hero">
        <h1 className="about-logo">RE<span className="sun">◍</span>DUNE</h1>
        <p className="about-tag">
          A complete, <b>100% in-browser</b> reverse-engineering studio for the 1992 Cryo classic <b>Dune</b>.
          Decode, view, edit and <b>re-pack</b> the game's graphics, rooms, music, dialogue, saves and archives —
          every codec a TypeScript port of the project's Python tools, validated byte-for-byte. You load{" "}
          <i>your own</i> legal game files; nothing is ever uploaded.
        </p>
        <div className="chips">
          <span className="chip"><b>13</b> studios</span>
          <span className="chip"><b>262</b> game files decoded</span>
          <span className="chip blue"><b>713</b> CONDIT entries</span>
          <span className="chip green"><b>byte-identical</b> round-trips</span>
          <span className="chip"><b>0</b> uploads — runs offline</span>
        </div>
      </div>

      <div className="feature-grid">
        {FEATURES.map((f) => (
          <div key={f.name} className="feature">
            <div className="feature-h">
              <span className="feature-ico">{f.ico}</span>
              <span className="feature-name">{f.name}</span>
            </div>
            <div className="feature-desc">{f.desc}</div>
          </div>
        ))}
      </div>

      <Panel title="Getting started">
        <div className="about-callout">
          <span className="ico">↥</span>
          <div className="small">
            Hit <b>“Open file…”</b> up top — or just <b>drag any Dune file onto the window</b> — and ReDune auto-detects
            the format and jumps to the right studio. From a repo clone, <code>npm run dev</code> serves the bundled{" "}
            <code>gamedata/</code> so you can load samples in one click; the Python{" "}
            <code>tools/extract_all.py</code> bulk-exports everything to PNG / WAV / JSON / MIDI.
          </div>
        </div>
      </Panel>
    </div>
  );
}

export function App() {
  const [tab, setTab] = useState<Tab>("sprites");
  const [pending, setPending] = useState<IncomingFile | null>(null);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState("");
  const openInput = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  /** Route a file to its tab by auto-detecting its format. */
  const openFile = (name: string, bytes: Uint8Array) => {
    let dest = null;
    try {
      dest = detectAssetType(name, bytes);
    } catch {
      dest = null;
    }
    if (!dest) {
      setNotice(`Couldn't auto-detect a format for "${name}" — pick a tab and load it there.`);
      return;
    }
    setPending({ tab: dest, name, bytes });
    setTab(dest);
    setNotice(`Opened ${name} → ${TAB_LABELS[dest]}`);
  };

  const readAndOpen = (f: File) => {
    const r = new FileReader();
    r.onerror = () => setNotice(`Couldn't read ${f.name} (${r.error?.message || "read error"})`);
    r.onload = () => {
      const buf = r.result as ArrayBuffer | null;
      if (!buf || buf.byteLength === 0) {
        setNotice(`${f.name} is empty — nothing to open.`);
        return;
      }
      openFile(f.name, new Uint8Array(buf));
    };
    r.readAsArrayBuffer(f);
  };

  const hasFiles = (dt: DataTransfer | null) => !!dt && Array.from(dt.types || []).includes("Files");

  return (
    <RoutedProvider value={{ pending, clear: () => setPending(null), open: openFile }}>
      <div
        className="app"
        onDragEnter={(e) => {
          if (hasFiles(e.dataTransfer)) {
            dragDepth.current++;
            setDragging(true);
          }
        }}
        onDragOver={(e) => {
          if (hasFiles(e.dataTransfer)) e.preventDefault();
        }}
        onDragLeave={() => {
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          if (e.dataTransfer.files[0]) readAndOpen(e.dataTransfer.files[0]);
        }}
      >
        <div className="row" style={{ alignItems: "baseline" }}>
          <h1 className="h1">REDUNE</h1>
          <span className="sub">Dune 1992 — Asset Studio · viewer · editor · recompiler</span>
          <span className="grow" />
          <button className="btn primary" onClick={() => openInput.current?.click()} title="Open any game file; the right tab is chosen automatically">
            ₕ Open file…
          </button>
          <input
            ref={openInput}
            type="file"
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files?.[0]) readAndOpen(e.target.files[0]);
              e.target.value = "";
            }}
          />
        </div>
        {notice && (
          <div className="small muted" style={{ marginTop: 4 }}>
            {notice}
          </div>
        )}
        <div className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={"tab" + (tab === t.id ? " active" : "")} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        <ErrorBoundary key={tab}>
          {tab === "sprites" && <SpriteViewer />}
          {tab === "rooms" && <RoomStudio />}
          {tab === "map" && <MapViewer />}
          {tab === "font" && <FontViewer />}
          {tab === "text" && <TextStudio />}
          {tab === "audio" && <AudioStudio />}
          {tab === "music" && <HeradStudio />}
          {tab === "video" && <HnmPlayer />}
          {tab === "story" && <StoryStudio />}
          {tab === "play" && <PlayRuntime />}
          {tab === "save" && <SaveEditor />}
          {tab === "condit" && <ConditStudio />}
          {tab === "archive" && <DatStudio />}
          {tab === "about" && <About />}
        </ErrorBoundary>
        <div className="sub" style={{ marginTop: 24, textAlign: "center", color: "var(--dim)" }}>
          Decoded in-browser · codecs ported from the ReDune Python toolkit · no game data is bundled
        </div>
        {dragging && (
          <div className="drop-overlay">
            <div className="drop-overlay-inner">Drop a Dune file — the right tab opens automatically</div>
          </div>
        )}
      </div>
    </RoutedProvider>
  );
}
