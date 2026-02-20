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

The CONDIT VM is a stack-based expression evaluator with 10 operations (comparisons, arithmetic, bitwise). The decompiler annotates GameStage comparisons with stage names.

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
lib/compression.py  — HSQ decompressor, F7 RLE codec
lib/constants.py    — Save offsets, game stages, equipment flags, CONDIT ops
tools/              — CLI tools built on lib/
ui/                 — React visualization
docs/               — Format specifications
```

## Key Discoveries

- **F7 RLE compression**: Save files use `F7 NN VV` run-length encoding (decoded from DuneEdit2's `SequenceParser.cs`)
- **CONDIT shared chains**: The 713 condition entries point into just 41 bytecode chains. Multiple dialogue/event indices share bytecode, entering at different offsets to evaluate different subsets of conditions.
- **GameStage (DS:0x2A)**: Single byte at save offset 0x4448 controls all story progression. Referenced 70+ times in CONDIT bytecodes.
- **16-hour days**: `GameElapsedTime & 0xF` = hour (0-15), `GameElapsedTime >> 4` = day number.

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## License

This is a reverse engineering research project. Game data files are not included. You need a legal copy of Dune (1992) to use these tools.
