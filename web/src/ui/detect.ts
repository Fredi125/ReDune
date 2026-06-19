/**
 * Auto-detect which studio tab a dropped/opened file belongs to.
 *
 * The `.HSQ` extension is heavily overloaded (sprites, CONDIT, DIALOGUE, PHRASE,
 * COMMAND, MAP, GLOBDATA, SN* sound, HERAD music), so detection is name-hint
 * first (most reliable for the canonical game files) then content-sniffed.
 */
import { hsqDecompress, isHsq } from "../codecs/compression";
import { isVoc } from "../codecs/voc";
import { looksLikeSprite } from "../codecs/sprite";
import { RES_MAP_SIZE } from "../codecs/map";

export type TabId =
  | "sprites"
  | "rooms"
  | "map"
  | "font"
  | "text"
  | "audio"
  | "music"
  | "video"
  | "story"
  | "save"
  | "condit"
  | "archive";

/** The 10 HERAD music stems (×3 variants: .HSQ/.AGD/.M32). */
const MUSIC_NAMES = new Set([
  "ARRAKIS", "BAGDAD", "CRYOMUS", "MORNING", "SEKENCE",
  "SIETCHM", "WARSONG", "WATER", "WORMINTR", "WORMSUIT",
]);

function baseName(name: string): string {
  const i = Math.max(name.lastIndexOf("/"), name.lastIndexOf("\\"));
  return i >= 0 ? name.slice(i + 1) : name;
}
function extOf(name: string): string {
  const m = /\.([^.]+)$/.exec(name);
  return m ? m[1].toUpperCase() : "";
}
function stemOf(name: string): string {
  const b = baseName(name).toUpperCase();
  const dot = b.lastIndexOf(".");
  return dot > 0 ? b.slice(0, dot) : b;
}

/**
 * Best-guess the studio tab for a file. Returns null when nothing matches
 * (caller should ask the user to pick a tab).
 */
export function detectAssetType(name: string, bytes: Uint8Array): TabId | null {
  const e = extOf(name);
  const s = stemOf(name);

  // 1) Unambiguous extensions.
  if (e === "SAV") return "save";
  if (e === "SAL") return "rooms";
  if (e === "VOC") return "audio";
  if (e === "HNM") return "video";
  if (e === "DAT") return "archive";
  if (e === "AGD" || e === "M32" || e === "MID") return "music";
  if (e === "BIN") {
    if (s.startsWith("TABLAT") || s.startsWith("GLOBDATA")) return "map";
    return "font"; // DNCHAR* and any other .BIN default to the font viewer
  }

  // 2) Name hints for the overloaded .HSQ extension (canonical game names).
  if (s === "MAP" || s.startsWith("GLOBDATA")) return "map";
  if (s.startsWith("CONDIT")) return "condit";
  if (s.startsWith("DIALOGUE")) return "story";
  if (s.startsWith("PHRASE") || s.startsWith("COMMAND")) return "text";
  if (MUSIC_NAMES.has(s)) return "music";
  if (/^SN[0-9A]$/.test(s)) return "audio"; // SN1..SN9, SNA

  // 3) Content sniffing (decompress HSQ containers first).
  let dec = bytes;
  if (isHsq(bytes)) {
    try {
      dec = hsqDecompress(bytes);
    } catch {
      dec = bytes;
    }
  }
  if (isVoc(bytes) || isVoc(dec)) return "audio";
  if (looksLikeSprite(dec)) return "sprites";
  if (dec.length === RES_MAP_SIZE) return "map";
  // HERAD: word at offset 2 is the track-data-start signature (0x0032 / 0x0052).
  if (dec.length >= 4) {
    const sig = dec[2] | (dec[3] << 8);
    if (sig === 0x0032 || sig === 0x0052) return "music";
  }

  // 4) Fallback: most remaining .HSQ files are sprite sheets.
  if (e === "HSQ") return "sprites";
  return null;
}

/** Human label for a tab id (for status messages). */
export const TAB_LABELS: Record<TabId, string> = {
  sprites: "Sprites",
  rooms: "Rooms",
  map: "Map",
  font: "Font",
  text: "Text",
  audio: "Audio",
  music: "Music",
  video: "Video",
  story: "Story",
  save: "Save editor",
  condit: "CONDIT studio",
  archive: "Archive",
};
