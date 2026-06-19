import { useRef, useState } from "react";
import { SpriteViewer } from "./ui/SpriteViewer";
import { SaveEditor } from "./ui/SaveEditor";
import { ConditStudio } from "./ui/ConditStudio";
import { RoomStudio } from "./ui/RoomStudio";
import { TextStudio } from "./ui/TextStudio";
import { MapViewer } from "./ui/MapViewer";
import { AudioStudio } from "./ui/AudioStudio";
import { StoryStudio } from "./ui/StoryStudio";
import { FontViewer } from "./ui/FontViewer";
import { DatStudio } from "./ui/DatStudio";
import { HnmPlayer } from "./ui/HnmPlayer";
import { HeradStudio } from "./ui/HeradStudio";
import { ErrorBoundary, Panel } from "./ui/shared";
import { RoutedProvider, type IncomingFile } from "./ui/routing";
import { detectAssetType, TAB_LABELS } from "./ui/detect";

type Tab = "sprites" | "rooms" | "map" | "font" | "text" | "audio" | "music" | "video" | "story" | "save" | "condit" | "archive" | "about";

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
  { id: "save", label: "⚔ Save editor" },
  { id: "condit", label: "⎔ CONDIT studio" },
  { id: "archive", label: "🗜 Archive" },
  { id: "about", label: "ⓘ About" },
];

function About() {
  return (
    <div className="col">
      <Panel title="ReDune — Dune (1992) Asset Studio">
        <p className="small">
          A fully client-side viewer / editor / recompiler for the 1992 Cryo game <b>Dune</b>. Every codec — HSQ &amp; F7
          (de)compression, sprite decoding, the save format, and the CONDIT bytecode VM (both directions) — is a
          TypeScript port of the project's Python tools, validated byte-for-byte against them. Nothing is uploaded:
          you load <i>your own</i> legal game files and everything is decoded in your browser.
        </p>
        <ul className="small">
          <li>
            <b>Sprites</b> — decode any sprite <code>*.HSQ</code> to canvas, export PNG, <b>replace frames with PNGs</b>
            and re-export a working <code>.HSQ</code> (graphics mods).
          </li>
          <li>
            <b>Rooms</b> — decode <code>*.SAL</code> room layouts, render them to canvas with their decoration
            sprites, edit/add/move sprite placements, and re-export a byte-perfect <code>.SAL</code>.
          </li>
          <li>
            <b>Map</b> — render <code>MAP.HSQ</code> world terrain as a heatmap, plus an experimental spinning{" "}
            <b>globe</b> projected from the GLOBDATA latitude scanlines.
          </li>
          <li>
            <b>Font</b> — view &amp; edit the <code>DNCHAR.BIN</code> bitmap font (pixel editor + live preview), re-export
            a byte-identical <code>.BIN</code>.
          </li>
          <li>
            <b>Text</b> — view/edit <code>PHRASE*.HSQ</code> dialogue and <code>COMMAND*.HSQ</code> UI strings
            (translations/mods) and re-export a working <code>.HSQ</code>.
          </li>
          <li>
            <b>Audio</b> — decode &amp; play sound effects (<code>SN*.HSQ/.VOC</code>); import a WAV and re-export a
            working <code>.VOC</code>/<code>.HSQ</code> (sound mods), or export WAV.
          </li>
          <li>
            <b>Music</b> — decode HERAD music + its OPL2 instrument patches, play it in-browser via a 2-operator FM
            synth driven by the real patches, and export a Standard MIDI file.
          </li>
          <li>
            <b>Video</b> — decode and play <code>*.HNM</code> cutscenes on canvas (frame stepper + soundtrack); export WAV.
          </li>
          <li>
            <b>Story</b> — cross-reference <code>DIALOGUE.HSQ</code> × <code>CONDIT.HSQ</code> × <code>PHRASE*.HSQ</code>:
            see every dialogue option with its gating condition and spoken line; edit records and re-export
            <code>DIALOGUE.HSQ</code>.
          </li>
          <li>
            <b>Save editor</b> — load <code>DUNE*.SAV</code>, edit globals / troops / sietches / NPCs / smugglers,
            export a working save.
          </li>
          <li>
            <b>CONDIT studio</b> — browse &amp; decompile the 713 condition entries, recompile expressions, patch
            in-place and re-export <code>CONDIT.HSQ</code>.
          </li>
          <li>
            <b>Archive</b> — open <code>DUNE.DAT</code>, extract/decompress any of its files, replace them with your
            edited assets, and rebuild a working <code>DUNE.DAT</code> — the full mod loop, all in-browser.
          </li>
        </ul>
        <p className="small muted">
          Tip: use <b>“Open file…”</b> at the top (or just <b>drag a file anywhere</b> onto the window) and ReDune picks
          the right tab automatically. To load the bundled samples with one click, run <code>npm run dev</code> from a
          repo clone (it serves <code>gamedata/</code>); otherwise use “Choose file…”. Run the Python{" "}
          <code>tools/extract_all.py</code> to bulk-export assets to PNG/WAV/JSON.
        </p>
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
    const dest = detectAssetType(name, bytes);
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
    r.onload = () => openFile(f.name, new Uint8Array(r.result as ArrayBuffer));
    r.readAsArrayBuffer(f);
  };

  return (
    <RoutedProvider value={{ pending, clear: () => setPending(null) }}>
      <div
        className="app"
        onDragEnter={(e) => {
          if (e.dataTransfer?.types?.includes("Files")) {
            dragDepth.current++;
            setDragging(true);
          }
        }}
        onDragOver={(e) => {
          if (e.dataTransfer?.types?.includes("Files")) e.preventDefault();
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
