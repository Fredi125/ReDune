import { useState } from "react";
import { SpriteViewer } from "./ui/SpriteViewer";
import { SaveEditor } from "./ui/SaveEditor";
import { ConditStudio } from "./ui/ConditStudio";
import { RoomStudio } from "./ui/RoomStudio";
import { TextStudio } from "./ui/TextStudio";
import { ErrorBoundary, Panel } from "./ui/shared";

type Tab = "sprites" | "rooms" | "text" | "save" | "condit" | "about";

const TABS: { id: Tab; label: string }[] = [
  { id: "sprites", label: "◳ Sprites" },
  { id: "rooms", label: "▦ Rooms" },
  { id: "text", label: "✎ Text" },
  { id: "save", label: "⚔ Save editor" },
  { id: "condit", label: "⎔ CONDIT studio" },
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
            <b>Sprites</b> — decode any sprite <code>*.HSQ</code> (palette + RLE/raw bipixels) to canvas; export PNG.
          </li>
          <li>
            <b>Rooms</b> — decode <code>*.SAL</code> room layouts, render them to canvas with their decoration
            sprites, edit/add/move sprite placements, and re-export a byte-perfect <code>.SAL</code>.
          </li>
          <li>
            <b>Text</b> — view/edit <code>PHRASE*.HSQ</code> dialogue and <code>COMMAND*.HSQ</code> UI strings
            (translations/mods) and re-export a working <code>.HSQ</code>.
          </li>
          <li>
            <b>Save editor</b> — load <code>DUNE*.SAV</code>, edit globals / troops / sietches, export a working save.
          </li>
          <li>
            <b>CONDIT studio</b> — browse &amp; decompile the 713 condition entries, recompile expressions, patch
            in-place and re-export <code>CONDIT.HSQ</code>.
          </li>
        </ul>
        <p className="small muted">
          Tip: to load files with one click, symlink or copy your extracted game files into <code>web/public/game/</code>{" "}
          (git-ignored). Otherwise use “Choose file…”. Run the Python <code>tools/extract_all.py</code> to bulk-export
          assets to PNG/WAV/JSON.
        </p>
      </Panel>
    </div>
  );
}

export function App() {
  const [tab, setTab] = useState<Tab>("sprites");
  return (
    <div className="app">
      <div className="row" style={{ alignItems: "baseline" }}>
        <h1 className="h1">REDUNE</h1>
        <span className="sub">Dune 1992 — Asset Studio · viewer · editor · recompiler</span>
      </div>
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
        {tab === "text" && <TextStudio />}
        {tab === "save" && <SaveEditor />}
        {tab === "condit" && <ConditStudio />}
        {tab === "about" && <About />}
      </ErrorBoundary>
      <div className="sub" style={{ marginTop: 24, textAlign: "center", color: "var(--dim)" }}>
        Decoded in-browser · codecs ported from the ReDune Python toolkit · no game data is bundled
      </div>
    </div>
  );
}
