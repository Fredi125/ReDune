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
│   └── constants.py    ← Game constants, offsets, enums
├── tools/              ← CLI tools
│   ├── save_editor.py       ← Read/write save files (F7 RLE, all fields)
│   ├── condit_decompiler.py ← CONDIT VM bytecode decompiler
│   ├── condit_recompiler.py ← CONDIT expression → bytecode compiler
│   ├── dialogue_decompiler.py ← DIALOGUE.HSQ bytecode decompiler
│   ├── dialogue_browser.py  ← CONDIT×DIALOGUE×PHRASE cross-reference browser
│   ├── phrase_dumper.py     ← PHRASE*.HSQ text string extractor
│   ├── npc_smuggler_decoder.py ← NPC & smuggler save data decoder
│   ├── sal_decoder.py       ← SAL scene layout decoder
│   ├── bin_decoder.py       ← BIN file decoder (font, tables, anim)
│   ├── sprite_decoder.py    ← Sprite/graphics HSQ decoder (palettes, pixels)
│   ├── map_decoder.py       ← MAP.HSQ world map decoder
│   ├── command_decoder.py   ← COMMAND.HSQ string table decoder
│   ├── hnm_decoder.py       ← HNM video file analyzer
│   ├── lop_decoder.py       ← LOP background animation decoder
│   ├── herad_decoder.py     ← HERAD AdLib/OPL2 music decoder (+ MIDI export)
│   ├── sound_decoder.py     ← VOC sound effect decoder (+ WAV export)
│   ├── file_index.py        ← Game file catalog (262 files, 18 categories)
│   └── hsq_decompress.py   ← HSQ file decompressor
├── ui/                 ← Web UI
│   └── save_explorer.jsx   ← React save file explorer
├── docs/               ← Technical documentation
│   ├── save_format.md      ← Complete save file map
│   ├── condit_vm.md        ← CONDIT VM architecture
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
| 0x451E | 1960 | Sietch block: 70 × 28 bytes |
| 0x4CC8 | 1836 | Troop block: 68 × 27 bytes |

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

- [x] Decode DIALOGUE.HSQ bytecode format → `tools/dialogue_decompiler.py`
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
- [x] Analyze HNM video files → `tools/hnm_decoder.py` (chunk structure, frame analysis)
- [x] Decode LOP background animations → `tools/lop_decoder.py` (4-phase PackBits, 152×190 blit)
- [x] Integrate CONDIT×DIALOGUE×PHRASE → `tools/dialogue_browser.py` (cross-reference browser)
- [x] HERAD music format decoder → `tools/herad_decoder.py` (10 AdLib/OPL2 tracks, event parsing)
- [x] HERAD → MIDI converter → `tools/herad_decoder.py --midi` (all 10 tracks exportable)
- [x] Decode VOC sound effects → `tools/sound_decoder.py` (6 SN*.HSQ files, WAV export)
- [x] Build game file catalog → `tools/file_index.py` (262 files, 18 categories)
- [x] Comprehensive format guide → `docs/file_formats.md` (all formats documented)

## Pending Work

### Low Priority
- [ ] HNM video frame pixel extraction (frame decoding beyond chunk analysis)
- [ ] Complete game state editor (troops + NPCs + smugglers + conditions)

## External References

- **Cryogenic (Spice86)**: https://github.com/OpenRakis/Cryogenic — C# reimplementation
- **OpenRakis**: https://github.com/OpenRakis/OpenRakis — DuneEdit2 + tools
- **DNCDPRG.ASM**: IDA disassembly of the DOS executable (in OpenRakis repo)
- **DuneEdit2**: Save editor with offset definitions for multiple game versions
