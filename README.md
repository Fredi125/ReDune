# dune1992-re

Reverse engineering and modding toolkit for **Dune** (1992, Cryo Interactive).

Targets the CD version 3.7 (`DNCDPRG.EXE`). Decoded from the DOS executable disassembly, cross-referenced with the [Cryogenic/Spice86](https://github.com/OpenRakis/Cryogenic) C# reimplementation and [DuneEdit2](https://github.com/OpenRakis/OpenRakis) source.

## Tools

### Save Editor (`tools/save_editor.py`)

Read and modify save game files. Handles F7 RLE compression transparently.

```bash
# View save file summary
python3 tools/save_editor.py DUNE37S1.SAV

# Edit game state
python3 tools/save_editor.py DUNE37S1.SAV --set stage=0x50 --set spice=9999 -o modified.SAV

# Edit troops and sietches
python3 tools/save_editor.py DUNE37S1.SAV --set-troop 5 job=4 equip=0xFF
python3 tools/save_editor.py DUNE37S1.SAV --set-sietch 3 water=255 spice=255

# Inspect data
python3 tools/save_editor.py DUNE37S1.SAV --troops
python3 tools/save_editor.py DUNE37S1.SAV --troop 5
python3 tools/save_editor.py DUNE37S1.SAV --hex 0x4448
```

**Editable fields:**
- Globals: `stage`, `spice`, `charisma`, `rallied`, `day`, `hour`, `contact`
- Troops: `job`, `population`, `motivation`, `spice_skill`, `army_skill`, `eco_skill`, `equipment`, `dissatisfaction`
- Sietches: `status`, `equipment`, `water`, `spice`, `spice_density`, `region`

### CONDIT Decompiler (`tools/condit_decompiler.py`)

Decompile the event condition bytecodes that gate dialogue and story events.

```bash
# Decompile all conditions
python3 tools/condit_decompiler.py CONDIT.HSQ

# Single entry with detail
python3 tools/condit_decompiler.py CONDIT.HSQ --entry 1

# Show the 41 shared bytecode chains
python3 tools/condit_decompiler.py CONDIT.HSQ --chains

# Statistics
python3 tools/condit_decompiler.py CONDIT.HSQ --stats
```

### CONDIT Recompiler (`tools/condit_recompiler.py`)

Compile human-readable expressions back into CONDIT bytecodes.

```bash
# Compile a single expression
python3 tools/condit_recompiler.py "byte[0x2A] == 0x50"

# Roundtrip test against original CONDIT.HSQ
python3 tools/condit_recompiler.py --test CONDIT.HSQ
```

### Dialogue Decompiler (`tools/dialogue_decompiler.py`)

Decompile DIALOGUE.HSQ bytecodes controlling NPC conversation triggers.

```bash
python3 tools/dialogue_decompiler.py DIALOGUE.HSQ --full
python3 tools/dialogue_decompiler.py DIALOGUE.HSQ --entry 5
python3 tools/dialogue_decompiler.py DIALOGUE.HSQ --stats
```

### Phrase Text Extractor (`tools/phrase_dumper.py`)

Extract dialogue text strings from PHRASE*.HSQ files.

```bash
python3 tools/phrase_dumper.py PHRASE11.HSQ --stats
python3 tools/phrase_dumper.py PHRASE11.HSQ --index 0x35
python3 tools/phrase_dumper.py PHRASE11.HSQ --search "spice"
python3 tools/phrase_dumper.py PHRASE11.HSQ --range 0x35-0x5E
```

### NPC & Smuggler Decoder (`tools/npc_smuggler_decoder.py`)

Decode NPC and smuggler data blocks from save files.

```bash
python3 tools/npc_smuggler_decoder.py DUNE37S1.SAV --npcs
python3 tools/npc_smuggler_decoder.py DUNE37S1.SAV --smugglers
python3 tools/npc_smuggler_decoder.py DUNE37S1.SAV --npc 3
```

### SAL Scene Decoder (`tools/sal_decoder.py`)

Decode room/scene layout files (sprite placement, polygons, UI regions).

```bash
python3 tools/sal_decoder.py PALACE.SAL --stats
python3 tools/sal_decoder.py PALACE.SAL --section 5
python3 tools/sal_decoder.py VILG.SAL --raw
```

### BIN File Decoder (`tools/bin_decoder.py`)

Decode DNCHAR font, TABLAT latitude table, VER animations, THE_END remap table.

```bash
python3 tools/bin_decoder.py DNCHAR.BIN --render          # ASCII font preview
python3 tools/bin_decoder.py DNCHAR.BIN --char 65         # single character 'A'
python3 tools/bin_decoder.py TABLAT.BIN
python3 tools/bin_decoder.py VER.BIN --raw
```

### HSQ Decompressor (`tools/hsq_decompress.py`)

Decompress HSQ (LZ77-variant) compressed game resources.

```bash
python3 tools/hsq_decompress.py CONDIT.HSQ
python3 tools/hsq_decompress.py DIALOGUE.HSQ PHRASE11.HSQ  # batch
python3 tools/hsq_decompress.py CONDIT.HSQ --info           # header only
```

### Save Explorer UI (`ui/save_explorer.jsx`)

Interactive React dashboard for exploring save file data. Shows globals, troops (with skill bars and filtering), sietches, and CONDIT bytecode chains.

## Architecture

```
lib/compression.py  — HSQ compressor/decompressor, F7 RLE codec
lib/constants.py    — Save offsets, game stages, DS variable map, equipment flags
tools/              — CLI tools built on lib/
ui/                 — React visualization
docs/               — Format specifications
```

## Key Discoveries

- **HSQ bit queue**: Each uint16 provides 16 raw data bits. The sentinel is added by the decompressor's `0x8000 | (word >> 1)`, not stored in the word. Header checksum: sum of all 6 bytes ≡ 0xAB (mod 256).
- **F7 RLE compression**: Save files use `F7 NN VV` run-length encoding (decoded from DuneEdit2's `SequenceParser.cs`)
- **CONDIT shared chains**: The 713 condition entries point into just 41 bytecode chains. Multiple dialogue/event indices share bytecode, entering at different offsets to evaluate different subsets of conditions.
- **GameStage (DS:0x2A)**: Single byte at save offset 0x4448 controls all story progression. Referenced 70+ times in CONDIT bytecodes.
- **16-hour days**: `GameElapsedTime & 0xF` = hour (0-15), `GameElapsedTime >> 4` = day number.
- **DNCHAR font format**: First 256 bytes = width table, bytes 256+ = 9-byte monochrome bitmaps. Confirmed from ASM: bitmap pointer `word_219C4 = 0CFECh` = load address + 256.
- **SAL scene layout**: 4 scene files define all room layouts with 1,758 sprites, 105 polygons, 20 rect fills total across 48 sections.

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## License

This is a reverse engineering research project. Game data files are not included. You need a legal copy of Dune (1992) to use these tools.
