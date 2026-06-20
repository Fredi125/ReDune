# CLAUDE.md — Dune 1992 Reverse Engineering Project

## Project Overview

Reverse engineering and modding toolkit for **Dune** (1992, Cryo Interactive, CD version 3.7).

This project decodes the game's binary formats through disassembly of `DNCDPRG.EXE`, cross-referencing with the [Cryogenic/Spice86](https://github.com/OpenRakis/Cryogenic) C# reimplementation and [DuneEdit2](https://github.com/OpenRakis/OpenRakis) save editor source.

## Repository Structure

```
dune1992-re/
├── CLAUDE.md           ← You are here
├── README.md           ← Project documentation
├── lib/                ← Shared Python library
│   ├── __init__.py
│   ├── compression.py  ← HSQ compressor/decompressor + F7 RLE codec
│   ├── png.py          ← Pure-stdlib PNG writer (RGB/RGBA) for export tools
│   └── constants.py    ← Game constants, offsets, enums
├── tools/              ← CLI tools (decoders, encoders, exporters)
│   ├── save_editor.py       ← Read/write save files (F7 RLE, all fields; --json)
│   ├── condit_decompiler.py ← CONDIT VM bytecode decompiler
│   ├── condit_recompiler.py ← CONDIT expression → bytecode compiler
│   ├── dialogue_decompiler.py ← DIALOGUE.HSQ bytecode decompiler
│   ├── dialogue_browser.py  ← CONDIT×DIALOGUE×PHRASE cross-reference browser
│   ├── phrase_dumper.py     ← PHRASE*.HSQ text string extractor
│   ├── npc_smuggler_decoder.py ← NPC & smuggler save data decoder
│   ├── sal_decoder.py       ← SAL scene layout decoder
│   ├── sal_encoder.py       ← SAL scene layout ENCODER (100% byte-identical round-trip)
│   ├── extract_all.py       ← Batch pipeline → web-ready PNG/WAV/JSON + manifest
│   ├── bin_decoder.py       ← BIN file decoder (font, tables, anim; --png)
│   ├── sprite_decoder.py    ← Sprite/graphics HSQ decoder (palettes, pixels; --png/--atlas)
│   ├── map_decoder.py       ← MAP.HSQ world map decoder
│   ├── command_decoder.py   ← COMMAND.HSQ string table decoder
│   ├── hnm_decoder.py       ← HNM video decoder (BMP frame + WAV audio export)
│   ├── lop_decoder.py       ← LOP background animation decoder
│   ├── herad_decoder.py     ← HERAD music decoder (HSQ/AGD/M32, 30 files + MIDI export)
│   ├── sound_decoder.py     ← VOC sound effect decoder (+ WAV export)
│   ├── dat_decoder.py       ← DUNE.DAT archive decoder & repacker (extract/repack/replace)
│   ├── globdata_decoder.py  ← GLOBDATA.HSQ decoder (gradients + globe projection)
│   ├── driver_decoder.py    ← DN*.HSQ sound-driver disassembler (OPL2 register map, ports, jump table)
│   ├── file_index.py        ← Game file catalog (262 files, 18 categories)
│   └── hsq_decompress.py   ← HSQ file decompressor
├── ui/                 ← Original single-file React save explorer (snapshot)
│   └── save_explorer.jsx   ← React save file explorer
├── web/                ← Web Asset Studio (Vite + React + TypeScript)
│   ├── src/codecs/         ← TS ports: compression, sprite, sal, text, voc, map, font, dialogue, condit, conditVM, save, globdata, dat, hnm, herad, tablat, palette (validated vs Python)
│   ├── src/ui/             ← Sprites, Rooms, Map, Font, Text, Audio, Music, Video, Story, Play, SaveEditor, ConditStudio, Archive
│   └── test/codecs.test.ts ← Byte-for-byte cross-check against lib/ using gamedata (83 checks)
├── docs/               ← Technical documentation
│   ├── save_format.md      ← Complete save file map
│   ├── condit_vm.md        ← CONDIT VM architecture
│   ├── adlib_driver.md     ← DN* sound drivers + OPL2 register map (from DNADL disasm)
│   └── file_formats.md     ← Game resource formats (HSQ, SAL, HNM, etc.)
└── samples/            ← Example data files (not game files)
```

## Key Technical Facts

### Save Files (DUNE*.SAV)
- **F7 RLE compressed**: ~13KB compressed → ~22KB decompressed
- Compression: `F7 01 F7` = literal 0xF7, `F7 NN VV` (NN>2) = repeat VV NN times
- All offsets in docs/code are into the **decompressed** data
- DuneEdit2 uses **1-indexed** offsets; we use **0-indexed** (subtract 1 to convert)

### Critical Save Offsets (0-indexed, CD v3.7)
| Offset | Size | Field |
|--------|------|-------|
| 0x4448 | 1 | **GameStage** — master story progression (0x00-0xC8) |
| 0x5592 | 2 | **DateTime** — bits[3:0]=hour(0-15), bits[15:4]=day |
| 0x44BE | 2 | Spice stockpile (uint16 LE, ×10 = displayed kg) |
| 0x4447 | 1 | Charisma (raw; GUI shows value/2) |
| 0x3338 | ~3960 | Dialogue state (DIALOGUE.HSQ byte 0 spoken flags) |
| 0x451E | 1960 | Sietch block: 70 × 28 bytes (names from COMMAND1.HSQ) |
| 0x4CC8 | 1836 | Troop block: 68 × 27 bytes |

### Sietch Record Layout (28 bytes, 0-indexed)
| Offset | Field | Notes |
|--------|-------|-------|
| +0x01 | Region | First name code (1-12, COMMAND[region-1]) |
| +0x02 | Subregion | Second name (1-2=faction, 3-11=Tabr..Pyort) |
| +0x09 | Appearance | ★ SAL file selector (see Room Layout below) |
| +0x0A | Troop ID | Housed troop (0-67) |
| +0x0B | Status | Bitfield: 0x10=inventory, 0x20=windtrap, 0x40=prospected, 0x80=undiscovered |
| +0x0C | Stage gate | GameStage threshold for discovery (0xFF=always) |
| +0x11 | Spice field | Unique spice field ID (1-76) |
| +0x12 | Spice amount | Stockpile at sietch |
| +0x13 | Spice density | Mining yield (0-250) |
| +0x15-0x1B | Equipment | 7 individual counts: Harv, Orni, Knif, Gun, Weird, Atom, Bulb |

### Room Layout Architecture (SAL Files + Appearance Byte)
- **4 SAL files** define all interior rooms: SIET(14sec), PALACE(15sec), VILG(11sec), HARK(8sec)
- **Appearance byte** (+0x09) selects SAL file via `calc_SAL_index` (CS1:0x5E4F):
  - `0x00-0x1F` → SIET.SAL, `0x20` → PALACE.SAL, `0x21-0x27` → VILG.SAL
  - `0x28-0x2F` → HARK.SAL, `0x30+` → HARK.SAL (clamped)
- **Sprite decoration HSQ** also selected: SIET→MAP2, PALACE→MIRROR, VILG→DS0, HARK→DS1
- **Section within SAL** selected by room navigation, NOT by appearance byte
- **SIET.SAL overlay sections**: 12=windtrap (status 0x20), 13=vegetation (status 0x01)

### DIALOGUE.HSQ (Dialogue Script Table)
- **NOT a bytecode VM** — fixed 4-byte record table referencing CONDIT and PHRASE
- 136 entries, 988 records, 480 unique phrase IDs
- Record: `[flags+action] [npc_id] [cond_type+menu+phrase_hi] [phrase_lo]`
- Full CONDIT index = `(cond_type * 256) + npc_id` (types 0/1/2 → indices 0-712)
- All 713 CONDIT entries are used by dialogue (0 unused)
- Save offset 0x3338: persists "spoken" flag (bit 7 of byte 0)

### CONDIT VM (Event Condition System)
- **CONDIT.HSQ**: 10,907 bytes decompressed, 713 entry offset table → 41 bytecode chains
- Stack-based expression evaluator with DX accumulator
- 10 operations at jump table `off_C246`: EQ, LT, GT, NE, LE, GE, ADD, SUB, AND, OR
- Operand encoding: `01 XX`=byte var, `00/02-7F XX`=word var, `80 XX`=imm8, `81-FF XXXX`=imm16
- Bytes 0x80-0xFE are separators (push to stack), 0xFF = terminator (unwind)
- **Key discovery**: Multiple entries share bytecode chains via offset overflow

### DNCDPRG.EXE Disassembly
- Primary source: `OpenRakis/asm/cd/DNCDPRG.ASM` (1MB IDA disassembly)
- CONDIT evaluator: `sub_C266` (main loop), `sub_C1DB` (operand reader), `sub_C204` (op dispatch)
- Data segment base: DS:0x1138

## Development Guidelines

### Adding New Tools
1. Put reusable logic in `lib/` (compression, parsing, constants)
2. CLI tools go in `tools/` — use argparse, support `--help`
3. Tools should `sys.path.insert(0, ...)` to find `lib/`
4. Use constants from `lib/constants.py`, don't hardcode offsets

### Testing
```bash
# Test save editor roundtrip
python3 tools/save_editor.py samples/DUNE37S1.SAV
python3 tools/save_editor.py samples/DUNE37S1.SAV --set stage=0x50 -o /tmp/test.SAV
python3 tools/save_editor.py /tmp/test.SAV --globals  # verify stage=0x50

# Test CONDIT decompiler
python3 tools/condit_decompiler.py samples/CONDIT.HSQ --entry 0
python3 tools/condit_decompiler.py samples/CONDIT.HSQ --stats
python3 tools/condit_decompiler.py samples/CONDIT.HSQ --chains
```

### Code Style
- Python 3.8+ compatible (no walrus operator in hot paths)
- Type hints on public functions
- Docstrings with format descriptions
- Hex values uppercase: `0x4448` not `0x4448`

## Completed Work

- [x] Decode DIALOGUE.HSQ record format → `tools/dialogue_decompiler.py` (136 entries, 988 records, NOT a VM)
- [x] Full DIALOGUE×CONDIT integration: CONDIT_idx = cond_type*256 + npc_id (all 713 CONDIT entries used)
- [x] Map DS variables from Cryogenic source → `lib/constants.py`
- [x] Build CONDIT recompiler → `tools/condit_recompiler.py` (63.7% roundtrip)
- [x] Decode NPC data block (save offset 0x53F4+) → `tools/npc_smuggler_decoder.py`
- [x] Map Smuggler data (0x54F6+) → `tools/npc_smuggler_decoder.py`
- [x] Build SAL scene decoder → `tools/sal_decoder.py`
- [x] HSQ compressor → `lib/compression.py` (186/186 files roundtrip)
- [x] Analyze PHRASE*.HSQ → `tools/phrase_dumper.py`
- [x] Decode BIN files (DNCHAR font, TABLAT, VER, THE_END) → `tools/bin_decoder.py`
- [x] Decode sprite/graphics HSQ format → `tools/sprite_decoder.py` (palettes, pixel data)
- [x] Decode MAP.HSQ world map → `tools/map_decoder.py` (320×152 tiles, regions, locations)
- [x] Decode COMMAND.HSQ string table → `tools/command_decoder.py` (all 186 HSQ files classified)
- [x] Decode HNM video format → `tools/hnm_decoder.py` (LZ frame decompression, BMP+WAV export)
- [x] Decode LOP background animations → `tools/lop_decoder.py` (4-phase PackBits, 152×190 blit)
- [x] Integrate CONDIT×DIALOGUE×PHRASE → `tools/dialogue_browser.py` (cross-reference browser)
- [x] HERAD music format decoder → `tools/herad_decoder.py` (10 tracks × 3 variants = 30 files)
- [x] HERAD → MIDI converter → `tools/herad_decoder.py --midi` (all 30 files, all variants)
- [x] HERAD AGD/M32 variant support → Tandy/PCjr + Roland MT-32 channelized MIDI
- [x] Decode VOC sound effects → `tools/sound_decoder.py` (6 SN*.HSQ files, WAV export)
- [x] Build game file catalog → `tools/file_index.py` (262 files, 18 categories)
- [x] Comprehensive format guide → `docs/file_formats.md` (all formats documented)
- [x] DUNE.DAT archive decoder → `tools/dat_decoder.py` (2549 files, list/extract/inspect)
- [x] Decode GLOBDATA.HSQ → `tools/globdata_decoder.py` (55 gradient tables + 64 globe scanlines)
- [x] DUNE.DAT repacker → `tools/dat_decoder.py --repack/--replace` (round-trip asset modification)
- [x] Decode room layout architecture → `lib/constants.py` (calc_SAL_index @ CS1:0x5E4F, appearance→SAL mapping)
- [x] Pure-stdlib PNG writer → `lib/png.py` (RGB/RGBA, used by all image exporters)
- [x] Sprite PNG/atlas export → `tools/sprite_decoder.py --png/--atlas` (PNG sheets + JSON atlas)
- [x] Image export for LOP / MAP / font → `--png` on `lop_decoder.py`, `map_decoder.py`, `bin_decoder.py`
- [x] JSON exporters → `--json` on condit/dialogue/phrase/command/save (machine-readable for the web app)
- [x] SAL scene ENCODER → `tools/sal_encoder.py` (**100% byte-identical round-trip on all 4 SAL files**)
- [x] Asset pipeline → `tools/extract_all.py` (gamedata → PNG/WAV/JSON/MIDI + manifest, **251/265** auto-extracted: sprites, sound, CONDIT/DIALOGUE/PHRASE/COMMAND, HNM→PNG+WAV, HERAD→MIDI, LOP→PNG, SAL→JSON, MAP→PNG, fonts→PNG, GLOBDATA/TABLAT/VER→JSON; only the 10 driver blobs + FREQ + 3 misc remain)
- [x] Web Archive tab "open →" routes any DUNE.DAT entry into the matching studio tab (`useOpen` + auto-detect)
- [x] Web Asset Studio → `web/` (Vite+React+TS; viewer/editor/recompiler, all in-browser)
- [x] TypeScript codec ports → `web/src/codecs/` (HSQ, F7, sprite, SAL, text, VOC, map, save, CONDIT decompile+recompile)
- [x] Codec parity tests → `web/test/codecs.test.ts` (35 checks, byte-for-byte vs Python on real game files)
- [x] Web Rooms tab → SAL decode/edit + canvas compositor (layout + decoration sprites) + byte-identical .SAL export
- [x] Web Text tab → PHRASE/COMMAND string editor (lossless edit form, re-export .HSQ) for translations/mods
- [x] Web Map tab → MAP.HSQ heatmap viewer; Web Audio tab → VOC sound playback + WAV export
- [x] CONDIT studio file-type detection (warns when a sprite/other HSQ is loaded instead of CONDIT)
- [x] Web Story tab → DIALOGUE×CONDIT×PHRASE cross-reference ("visual novel" tier: option, gating condition, spoken line)
- [x] Web Font tab → DNCHAR.BIN bitmap-font viewer (glyph atlas + live proportional text preview)
- [x] Web Archive tab → DUNE.DAT extract/replace/rebuild in-browser (byte-identical builder; closes the mod loop)
- [x] SAL polygon gradient shading → GLOBDATA gradient tables (subtype&0x7F → table → room palette), filled rooms
- [x] Web Video tab → HNM cutscene player (decode + canvas playback + soundtrack); frame checksums match Python
- [x] Web Music tab → HERAD decoder + MIDI export (OPL2/AGD/M32; byte-identical MIDI vs Python)
- [x] DIALOGUE/font/VOC re-encoders → `exportDialogueHsq`, `encodeDnchar` (byte-identical), `encodeVoc`/`wavToSamples` (WAV→VOC import); editable Story tab, font pixel editor, Audio "Replace from WAV"
- [x] Global auto-detect "Open file…" + window drag-and-drop → `web/src/ui/detect.ts` (extension + name hints + content sniff) routes any file to the right tab (`useIncoming` in every tab); verified by routing tests
- [x] Resilience pass → FileReader error/empty guards (shared LoadBar + App), try/catch in `useIncoming` (always clears), GLOBDATA.bin → Map routing

## Pending Work

### Medium Priority
- [ ] In-browser OPL2/MT-32 synthesis for true HERAD playback (currently MIDI export only)

- [x] True MAP globe projection → `MapViewer` globe mode wraps the **real
  MAP.HSQ terrain** onto the sphere (GLOBDATA longitude ramps + TABLAT
  foreshortening + limb shading) with a Dune desert palette (`map.ts planetColor`),
  replacing the row-major heatmap. Verified: real terrain varies across the disc
  over the full pole-to-pole row span. Falls back to GLOBDATA bytes if MAP absent.

- [x] CONDIT VM **evaluator** (runtime, not just decompiler) → `web/src/codecs/conditVM.ts`
  (`evalCondit`/`evalBytecode`, faithful sub_C266 stack machine) + new **Play tab**:
  load DIALOGUE+CONDIT(+PHRASE), edit game state (GameStage + flags), and each
  dialogue option shows AVAILABLE/blocked live as the real condition VM evaluates
  it against the state. Verified: all 713 entries evaluate; intro-only lines
  (`GameStage == 0x00`) gate off and late-game lines (`>u 0x2F`) unlock.
- [x] Play tab → **scene player**: shared `ui/RoomCanvas.tsx` (extracted from Rooms)
  renders a SAL room backdrop (+ decoration sheet + GLOBDATA gradients); a save's
  NPC roster (`allNpcs`) is clickable → opens each NPC's `forDialogue` entry
  (verified 15/16 sample NPCs map to non-empty entries; the 16th is the 0xFF "none").

- [x] Palette colour-cycling → `web/src/codecs/palette.ts` (`detectCycleRanges`
  finds smooth contiguous ramps; `rotatePalette` rotates them) + animated
  shimmer preview in the Sprites tab (toggle, per-ramp checkboxes, speed). The
  exact engine cycle ranges live in DNCDPRG.EXE; these are heuristic candidates.
- [x] FREQ.HSQ identified — not a data table but a ~1.27 s **silent** 8-bit /
  22 222 Hz VOC calibration buffer ("Sample test to calc freq" + 28 224 × 0x80).
  No decoder needed; documented so it's not mistaken for game audio.

- [x] HERAD OPL2/AGD event parser verified against adplug's CheradPlayer
  (herad.cpp): adplug's current model does **not** fit Cryo's files (recovers
  ~1.5k of ~24k notes, kills ~20 tracks), so Dune predates that revision. The
  restricted status set `{0x80,0x90,0xC0,0xD0,0xFF}` with 0xD0 as a 2-byte event
  is correct here (perfectly balanced note on/off). Documented in `herad.ts` /
  `tools/herad_decoder.py`; locked with a note-balance regression test. No code
  change warranted — adopting the adplug dispatch would regress.

- [x] CONDIT recompiler roundtrip 63.7% → **100% (713/713)**: op-byte is the
  word-pointer jump-table offset, so `op_index = (byte & 0x1F) >> 1` (was read as
  `byte & 0x1F`, mislabeling operators and leaving AND/OR as `?16`/`?18`); word
  vars emit type byte `0x02` (was `0x00`). Fixed in `web/src/codecs/condit.ts`,
  `tools/condit_decompiler.py`, `tools/condit_recompiler.py`; docs/condit_vm.md
  corrected. All 713 entries now decompile to readable, correct operators.

- [x] Sprite re-encoder → `web/src/codecs/sprite.ts encodeSpriteFile` (raw mode, decode-equivalent round-trip) + PNG import in Sprites tab
- [x] Complete game state editor → NPCs + smugglers added to the web Save editor (offsets verified vs Python)
- [x] MAP globe view → `web/src/codecs/globdata.ts parseGlobe` (64 latitude scanlines, verified vs Python) + experimental sphere render in the Map tab

- [x] In-browser HERAD playback → Music tab plays decoded note events via a WebAudio synth
- [x] HERAD OPL2 instrument-patch format decoded (`parseInstruments`, 40-byte records; verified) + 2-op WebAudio FM synth driven by the real patches (`web/src/audio/heradFm.ts`)
- [x] TABLAT.BIN globe latitude table decoded (`web/src/codecs/tablat.ts`, verified vs Python); its `scale` column = 199·cos(lat) confirms the sphere geometry and drives the globe foreshortening

- [x] Sound-driver disassembly → `tools/driver_decoder.py` + `docs/adlib_driver.md`:
  the `DN*.HSQ` drivers are HSQ-compressed 8086 with a common 7-entry jump-table
  ABI. Extracted the **exact OPL2 register map** from DNADL (ground truth, not
  adplug): write routine @0xA35 (port 0x388/0x389 + delay loops, reg=AL/val=AH),
  operator-slot tables @0x71/0x7A, instrument groups 0x20/0x40/0x60/0x80/0xE0+slot
  & 0xC0+ch (@0x958), and the 12-note F-number table @0x47 → 0xA0/0xB0. The fnum
  table is equal-tempered (≤~8 cents), confirming `heradFm.ts` tuning is correct.

### Low Priority (blocked on disassembly we don't have)
- [ ] Cycle-exact YM3812 (OPL2) emulator for bit-perfect HERAD timbre (current FM synth is a faithful 2-op approximation)
- [ ] Byte-exact MAP globe palette/orientation from the ASM (sub_1BA75) — geometry is validated (TABLAT) and the real MAP terrain is now wrapped on the sphere with a plausible desert palette; only the exact in-game palette + longitude origin remain (unpublished)

## External References

- **Cryogenic (Spice86)**: https://github.com/OpenRakis/Cryogenic — C# reimplementation
- **OpenRakis**: https://github.com/OpenRakis/OpenRakis — DuneEdit2 + tools
- **DNCDPRG.ASM**: IDA disassembly of the DOS executable (in OpenRakis repo)
- **DuneEdit2**: Save editor with offset definitions for multiple game versions
