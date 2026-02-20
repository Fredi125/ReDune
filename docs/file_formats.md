# Dune 1992 Game Resource Formats

Complete format documentation for Dune (1992, Cryo Interactive, CD version 3.7).
Decoded from DNCDPRG.EXE disassembly and the [Cryogenic](https://github.com/OpenRakis/Cryogenic) reimplementation.

---

## HSQ Compression

LZ77-variant used for most game resources (`.HSQ` extension). 186 resource files use this format.

### Header (6 bytes)
```
Offset  Size  Field
0x00    2     Decompressed size (uint16 LE)
0x02    1     Checksum byte
0x03    2     Compressed size (uint16 LE, == file size)
0x05    1     Checksum byte
```

**Header checksum**: Sum of all 6 header bytes ≡ 0xAB (mod 256). Byte 2 is always 0x00 in game files.

### Bitstream Decoder

Uses a 16-bit queue with sentinel mechanism. Each uint16 provides 16 raw data bits.
The decompressor adds the sentinel implicitly via `queue = 0x8000 | (word >> 1)`.

- **Bit 1**: Literal byte follows
- **Bit 0, Bit 1**: Long back-reference
  - uint16 word: bits[2:0] = count, bits[15:3] = 13-bit offset
  - If count == 0: read extra byte for count (0 = EOF, else copy count+2 bytes)
  - Otherwise: copy count+2 bytes from offset
  - Offset encoding: `(word >> 3) - 8192` (signed negative)
- **Bit 0, Bit 0**: Short back-reference
  - 2 more bits for count (0-3), 1 byte for offset
  - Copy count+2 bytes from `(byte - 256)` offset

### Compression

Compressor uses hash-chain LZ77 matching (32K hash table, chain depth 64).
All 186 game HSQ files roundtrip correctly through decompress→compress→decompress.

Reference: `lib/compression.py` — `hsq_compress()`, `hsq_decompress()`

---

## DIALOGUE.HSQ (Dialogue Bytecode)

Event/dialogue condition bytecodes controlling NPC conversations and story triggers.

### Structure
- **Offset table**: N × uint16 LE pointing to bytecode start positions
  - N = first_offset / 2
- **Bytecodes**: Condition chains evaluated by the dialogue VM

### Bytecode Format
- `00` / `02-7F` followed by byte: word variable operand (DS offset)
- `01` followed by byte: byte variable operand (DS offset)
- `80` followed by byte: 8-bit immediate value
- `81-FE` followed by uint16 LE: 16-bit immediate value (tag = count)
- `80-FE` alone: separator (pushes accumulator to stack)
- `FF`: terminator (unwinds evaluation)

### Operations (Jump table at `off_C246`)
```
0: EQ  (==)    5: GE  (>=)
1: LT  (<)     6: ADD (+)
2: GT  (>)     7: SUB (-)
3: NE  (!=)    8: AND (&)
4: LE  (<=)    9: OR  (|)
```

Reference: `tools/dialogue_decompiler.py`

---

## CONDIT.HSQ (Event Condition System)

Stack-based expression evaluator controlling game event triggers.

### Key Facts
- 10,907 bytes decompressed
- 713 entry offset table → 41 unique bytecode chains
- Multiple entries share chains via offset overlap
- Evaluator: `sub_C266` (main loop), `sub_C1DB` (operand reader)

### Recompilation
Expressions can be recompiled back to bytecodes. Example:
```
byte[0x2A] == 0x50  →  01 2A 80 50 00 FF
```

Roundtrip accuracy: 63.7% of original bytecodes match exactly (differences due
to equivalent encodings: byte vs word operands, different immediate widths).

Reference: `tools/condit_decompiler.py`, `tools/condit_recompiler.py`

---

## PHRASE*.HSQ (Dialogue Text Strings)

Packed string table for dialogue and UI text.

### Structure
- **Header**: uint16 LE offset to string data start
- **Index table**: N × uint16 LE offsets (relative to data start)
- **String data**: Null-terminated strings, one per index entry

### Encoding
- Standard ASCII text with inline formatting codes
- Phrase files: PHRASE11.HSQ through PHRASE14.HSQ (language variants)
- String indices correspond to DIALOGUE bytecode references

Reference: `tools/phrase_dumper.py`

---

## SAL (Scene Assembly Layout)

Room/scene layout format defining sprite placement, polygons, and UI regions.

### Files
| File | Sections | Sprites | Polygons | Rect fills |
|------|----------|---------|----------|------------|
| VILG.SAL | 11 | 407 | 34 | 3 |
| PALACE.SAL | 15 | 677 | 36 | 8 |
| SIET.SAL | 14 | 475 | 26 | 7 |
| HARK.SAL | 8 | 199 | 9 | 2 |

### Structure
```
Offset table: N × uint16 LE (N = first_offset / 2)
Per section:
  - 1 byte: sprite slot count
  - Command stream until 0xFFFF terminator
```

### Command Types

**Sprite** (most common): `sprite_id > 0x01, !(mod & 0x80)`
- 5 bytes: sprite_id, modifier, x (uint16 LE), y_byte
- modifier bits control flipping, layering

**Marker**: `sprite_id == 0x01`
- 5 bytes: navigation hotspots, NPC positions, interaction zones

**Polygon**: `mod & 0x80, !(mod & 0x40)`
- Variable length: color byte + 12-bit packed vertex coordinates
- Used for floors, walls, shaped regions

**Rect Fill**: `mod & 0x80, mod & 0x40`
- 10 bytes: solid color rectangle (x, y, w, h, color)

Source: OpenRakis `dunesal.c`
Reference: `tools/sal_decoder.py`

---

## BIN Files

Uncompressed binary data files with various formats.

### DNCHAR.BIN / DNCHAR2.BIN (Game Font)

2304 bytes. Bitmap font used for in-game text rendering.

```
Offset   Size   Field
0x000    256    Width table (1 byte per character, values 2-8 pixels)
0x100    2048   Bitmap data (227 chars × 9 bytes, 9 rows × 8px mono)
```

- Loaded at DS:0x0CEECh; bitmap pointer `word_219C4` = 0x0CFECh (= load + 256)
- Font renderer: `sub_1D096` in DNCDPRG.ASM
- DNCHAR2.BIN: alternate charset used when language_setting == 6 (Fremen/Dutch)
- Character rendering: MSB-first monochrome, 8 pixels wide, variable display width

### TABLAT.BIN (Latitude Table)

792 bytes = 99 × 8-byte records. Globe/map latitude lookup for the world view.

Each 8-byte record maps a latitude index to rendering parameters.

### VER.BIN (Vertex Animation)

1532 bytes. Intro/version screen vertex animation paths.

```
Header: 12 × uint16 LE offset table (6 entries × 2)
Data: 13-byte vertex groups defining animation keyframes
```

### THE_END.BIN (Identity Remap Table)

4096 bytes = 2048 × uint16 LE. Sequential identity mapping (value[i] = i).
Used as a default/passthrough palette remapping table for the ending sequence.

Reference: `tools/bin_decoder.py`

---

## Save Files (DUNE*.SAV)

### F7 RLE Compression

~13KB compressed → ~22KB decompressed.

```
F7 01 F7    → literal 0xF7 byte
F7 NN VV    → repeat byte VV exactly NN times (NN > 2)
other       → literal byte
```

### Critical Offsets (0-indexed, CD v3.7)

| Offset | Size | Field |
|--------|------|-------|
| 0x4448 | 1 | GameStage — master story progression (0x00-0xC8) |
| 0x5592 | 2 | DateTime — bits[3:0]=hour(0-15), bits[15:4]=day |
| 0x44BE | 2 | Spice stockpile (uint16 LE, ×10 = displayed kg) |
| 0x4447 | 1 | Charisma (raw; GUI shows value/2) |
| 0x451E | 1960 | Sietch block: 70 × 28 bytes |
| 0x4CC8 | 1836 | Troop block: 68 × 27 bytes |
| 0x53F4 | 254 | NPC block: 16 × ~16 bytes |
| 0x54F6 | ~156 | Smuggler block: 6 × 26 bytes |

### NPC Data (16 entries at 0x53F4)

Each NPC record stores location, dialogue state, and status flags.
Known NPCs: Duncan Idaho, Gurney Halleck, Stilgar, Liet Kynes, Chani, Harah,
Jessica, Thufir Hawat, Baron Harkonnen, Feyd-Rautha, Emperor, Princess Irulan,
Smuggler contacts, Fremen leaders.

### Smuggler Data (6 entries at 0x54F6)

Each 26-byte record: type, location, spice price, equipment price,
available equipment, trade flags.

Reference: `tools/save_editor.py`, `tools/npc_smuggler_decoder.py`

---

## MAP.HSQ (World Map Terrain)

50,681 bytes decompressed (`RES_MAP_SIZE = 0x0C5F9`).

Terrain/region data for the flat map and globe views. Each byte encodes terrain
type used for rendering and gameplay (spice fields, sietches, rocky terrain, sand).

Accessed linearly for the flat map, and via TABLAT.BIN latitude lookup for the
globe projection.

### Related ASM Functions
- `sub_1B58B`: map access using TABLAT latitude offsets
- `sub_1B427`: map data conversion (2-bit extraction)
- `sub_1B473`: map region overlay (2-bit bitfield insert)

### Related Resources
- **TABLAT.BIN**: 99 × 8-byte latitude lookup table
- **GLOBDATA.HSQ**: globe rendering parameters

Reference: `tools/map_decoder.py`

---

## GLOBDATA.HSQ (Globe Rendering Data)

16,091 bytes decompressed. Data for the 3D globe/world map view.

Contains coordinate lookup tables, region boundaries, and rendering parameters
for the spinning globe animation in the game's map screen.

---

## Sprite Graphics (133 HSQ files)

Character portraits, backgrounds, UI elements, and game sprites.
Format based on OpenRakis `dunespr.c`.

### File Structure (decompressed)
```
uint16 LE at offset 0 → pointer to offset table (= end of palette data)
Palette data:       bytes 2..pal_end (VGA color chunks)
Offset table:       N × uint16 LE at pal_end (sprite offsets relative to pal_end)
Sprite data:        4-byte headers + 4-bit bipixel pixel data
```

### Palette Chunks
```
start_index (byte), count (byte), count × 3 bytes (R, G, B, 6-bit VGA 0-63)
Terminator: 0xFF 0xFF
```

### Sprite Header (4 bytes)
```
byte 0:  width_low
byte 1:  bit7 = compression flag, bits 6-0 = width_high
byte 2:  height
byte 3:  palette_offset (base color index)
```
Width = `width_low | (width_high << 8)` (15-bit).

### Pixel Data
4-bit color indices packed as bipixels (2 pixels per byte):
- Low nibble = first pixel, high nibble = second pixel
- Final color = `palette_offset + nibble_value`

**Uncompressed**: pairs of bytes → 4 pixels per pair, scanline wrap at width.

**RLE compressed**: signed repetition codes with 4-byte scanline alignment:
- Negative code: repeat 1 bipixel `(-code + 1)` times
- Positive code: read `(code + 1)` literal bipixels

### File Categories
- **Backgrounds** (320×152): DH*, DN2*, DP*, DS*, DV*, DF*, INT*, VG*, VIL*, etc.
- **Portraits**: CHAN (42×26 thumbs + 120×94 main), EMPR, FEYD, GURN, STIL, etc.
- **UI/Icons**: GENERIC (91 sprites), ICONES (77), ONMAP (155×15x15)
- **Scenes**: BACK (320×152), BOOK, FRESK, FRM1-3, MIRROR, STARS

Reference: `tools/sprite_decoder.py`, OpenRakis `dunespr.c`

---

## COMMAND*.HSQ (String Tables)

UI text strings for the game interface. 7 language variants (COMMAND1-7).

### Structure
```
Offset table: N × uint16 LE (N = first_offset / 2)
String data:  0xFF-terminated ASCII strings
```

### Content (COMMAND1 = English, 333 strings)
```
  0-22:    Location names (Arrakeen, Carthag, Tabr, Tuek, etc.)
  23-46:   Job descriptions (Spice Mining, Military Training, etc.)
  47-66:   Status format templates (with inline variable placeholders)
  67-74:   Location type labels (Sietch, Palace, Village, Fort)
  75-80:   Battle/troop UI commands
  241:     Copy protection question
  259-301: Character names (Paul, Leto, Jessica, Stilgar, Chani, etc.)
  279-286: Intro story text
  305-332: Debug/cheat menu commands
```

Reference: `tools/command_decoder.py`

---

## SN*.HSQ (Creative Voice Files)

Sound Blaster digitized audio in Creative Voice File (VOC) format.
6 files: SN1-SN4, SN6, SNA.

### VOC Header (26 bytes)
```
Offset  Size  Field
0x00    20    Magic: "Creative Voice File\x1A"
0x14    2     Header size (uint16 LE, always 0x001A = 26)
0x16    2     Version (uint16 LE, typically 0x010A = 1.10)
0x18    2     Version check (uint16 LE, 0x1129 + version)
```

### VOC Data Blocks

| Type | Name | Data | Description |
|------|------|------|-------------|
| 0x01 | Sound data | sr_byte + codec + samples | Digitized audio |
| 0x03 | Silence | length (uint16 LE) + sr_byte | Silent gap |
| 0x06 | Repeat start | count (uint16 LE) | Loop begin (0xFFFF = infinite) |
| 0x07 | Repeat end | (empty) | Loop end |
| 0x00 | Terminator | — | End of file |

Block header: `type` (1 byte) + `length` (24-bit LE, 3 bytes).

**Sound data block** (type 0x01):
- `sr_byte`: sample rate = `1000000 / (256 - sr_byte)`
- `codec`: 0x00 = 8-bit unsigned PCM
- Sample data: `length - 2` bytes

### Sound Effects

| File | Rate (Hz) | Duration | Blocks | Description |
|------|-----------|----------|--------|-------------|
| SN1.HSQ | 10,416 | 1.82s | 3 (repeat ∞) | Worm / sandstorm |
| SN2.HSQ | 12,658 | 1.54s | 1 | Ornithopter engine |
| SN3.HSQ | 6,756 | 2.91s | 1 (repeat ∞) | Spice harvester |
| SN4.HSQ | 14,285 | 0.65s | 1 | Click/beep |
| SN6.HSQ | 8,928 | 2.34s | 2 (repeat 30+5) | Multi-part effect |
| SNA.HSQ | 7,692 | 2.48s | 2 (repeat ∞) | Ambient sound |

Reference: `tools/sound_decoder.py`

---

## FREQ.HSQ (Frequency Sample)

Sound frequency calibration sample. Starts with `"Sample test to calc freq"`.
Raw PCM data (unsigned 8-bit) used for sound card frequency detection.

---

## DN*.HSQ (x86 Driver Overlays)

Executable code overlays loaded as hardware drivers. 10 files.
Start with x86 JMP instructions (`E9` near jump, `EB` short jump).

| File | Driver |
|------|--------|
| DNVGA.HSQ | VGA graphics driver |
| DN386.HSQ | 386 protected mode driver |
| DNADG.HSQ | AdLib Gold sound driver |
| DNADL.HSQ | AdLib/OPL2 sound driver |
| DNADP.HSQ | AdLib Pro driver |
| DNMID.HSQ | MIDI driver |
| DNPCS.HSQ | PC Speaker driver |
| DNPCS2.HSQ | PC Speaker driver (variant) |
| DNSBP.HSQ | Sound Blaster Pro driver |
| DNSDB.HSQ | Sound Blaster driver |

---

## Complete HSQ File Classification (186 files)

| Category | Count | Description |
|----------|-------|-------------|
| Sprite Graphics | 133 | Portraits, backgrounds, UI, animations |
| Phrase Text | 14 | Dialogue strings (7 languages × 2 parts) |
| HERAD Music | 10 | OPL2/AdLib music tracks |
| x86 Drivers | 10 | Hardware driver overlays |
| String Tables | 7 | UI text (7 language variants) |
| Creative Voice | 6 | VOC sound effects |
| Map Data | 3 | World map, globe data |
| VM Bytecodes | 2 | CONDIT conditions, DIALOGUE triggers |
| Sound Sample | 1 | Frequency calibration |

---

## HNM (Video)

Cryo Interactive proprietary video format (`*.HNM`). Used for intro, cutscenes, and ending.

### Structure

Chunk-based format. Each chunk starts with `uint16 LE chunk_size`.

**Chunk 0 (header)**:
- VGA palette data (same format as sprite files: start, count, RGB×3)
- Terminated by `0xFFFF`
- Followed by frame offset table

**Subsequent chunks (frames)**: sub-chunks with 2-byte ASCII tags:

| Tag | Type | Description |
|-----|------|-------------|
| `sd` | Sound | Digitized audio data |
| `pl` | Palette | Palette update |
| `pt` | Unknown | — |
| `kl` | Unknown | — |
| other | Video | Frame data: bits[8:0]=width, byte[2]&0xFF=height, byte[3]=mode |

**Video frame decompression**:
- Checksum 0xAB (171): HSQ-style LZ77 decompression
- Checksum 0xAD (173): Codebook-based with RLE

Resolution: 320×200 (video area 320×152 + status bar).

Reference: `tools/hnm_decoder.py`, OpenRakis `HNMExtractor.cpp`

---

## LOP (Loop Animation)

Ambient animation loops for location backgrounds (`*.LOP`). 6 files.
4 sections per file likely correspond to time-of-day phases (dawn, day, dusk, night).

### Header (24 bytes)
```
Offset  Size  Field
0x00    2     Header size (uint16 LE, always 0x0018 = 24)
0x02    2     Marker (uint16 LE, always 0xFFFF)
0x04    4     Section 0 offset (uint32 LE, relative to header end)
0x08    4     Section 1 offset
0x0C    4     Section 2 offset
0x10    4     Section 3 offset
0x14    4     End offset (= total data size after header)
```

### Section Structure (per section)
```
Offset  Size  Field
+0x00   2     Section size (uint16 LE, including this field)
+0x02   1     X offset (blit position on 320×200 screen)
+0x03   1     Y offset
+0x04   1     Width (pixels)
+0x05   1     Mode (0xFE=opaque, 0xFF=transparent-zero)
+0x06   1     Flags (bit 7: PackBits compressed)
+0x07   1     Height (pixels)
+0x08   1     Reserved (always 0x00)
+0x09   2     Data size (= section_size - 6)
+0x0B   N     Compressed pixel data
```

### PackBits Compression

Per scanline (width pixels):
- `cmd & 0x80`: RLE — repeat next byte `(257 - cmd)` times
- Else: literal — copy `(cmd + 1)` bytes as-is

### Files
| File | Size | Description |
|------|------|-------------|
| MNT1.LOP | 38,315 | Mountain sietch type 1 |
| MNT2.LOP | 38,331 | Mountain sietch type 2 |
| MNT3.LOP | 58,419 | Mountain sietch type 3 |
| MNT4.LOP | 58,189 | Mountain sietch type 4 |
| PALACE.LOP | 34,965 | Arrakeen Palace exterior |
| SIET.LOP | 35,616 | Generic sietch exterior |

Reference: `tools/lop_decoder.py`

---

## HERAD (Music)

Cryo's proprietary OPL2/AdLib music format ("Hérault").

### Header (50 bytes, 0x00-0x31)
```
Offset  Size  Field
0x00    2     Instrument block offset (uint16 LE)
0x02    2     Track 0 offset (always 0x0032 = 50, also signature)
0x04    2+    Track 1..N offsets (uint16 LE, 0x0000 = end)
...           Zero padding to 0x2C
0x2C    2     Number of instruments (uint16 LE)
0x2E    2     Param2 — tempo/speed related (uint16 LE)
0x30    2     Param3 — loop count (uint16 LE)
```

**Identification**: Word at offset 2 is always `0x0032` (= 50, the data start offset).

### Track Data (offset 0x32 to instrument_offset)

Each track begins with a 2-byte header:
- Byte 0: initial delay (single byte, typically 0x00-0x7F)
- Byte 1: voice assignment (0x04 on track 0, 0xFF on tracks 1-8)

### Event Stream (MIDI-like)

| Status | Name | Data | Description |
|--------|------|------|-------------|
| 0x90 | Note On | note, velocity | Start playing note |
| 0x80 | Note Off | note, velocity | Stop playing note |
| 0xC0 | Program Change | instrument | Select OPL2 instrument |
| 0xD0 | Control | param, value | Parameter change |
| 0xFF | Voice/Sync | — | Channel marker |

**Delta time encoding**: If next byte is a status byte (0x80/0x90/0xC0/0xD0/0xFF),
implicit delta = 0. Otherwise, read VLQ-encoded delta time before the status byte.
VLQ uses standard bit-7 continuation; only 0x81-0x8F appear as continuations in practice.

### Instrument Definitions (at instrument_offset)

OPL2/FM synthesis register data, 11+ bytes per instrument:
modulator registers, carrier registers, feedback/connection byte.

### Music Files

| File | Size | Tracks | Notes | Instruments | Description |
|------|------|--------|-------|-------------|-------------|
| ARRAKIS.HSQ | 6,330 | 9 | 3,637 | 6 | Main Arrakis theme |
| BAGDAD.HSQ | 6,764 | 9 | 3,954 | 8 | Smuggler theme |
| CRYOMUS.HSQ | 786 | 9 | 308 | 3 | Cryo logo jingle |
| MORNING.HSQ | 6,378 | 9 | 3,466 | 6 | Dawn theme |
| SEKENCE.HSQ | 7,036 | 9 | 3,656 | 8 | Cutscene music |
| SIETCHM.HSQ | 3,804 | 9 | 2,254 | 5 | Sietch interior |
| WARSONG.HSQ | 4,126 | 9 | 2,748 | 6 | Battle music |
| WATER.HSQ | 5,740 | 9 | 2,788 | 6 | Ecology theme |
| WORMINTR.HSQ | 3,052 | 9 | 1,766 | 5 | Worm encounter |
| WORMSUIT.HSQ | 7,476 | 9 | 4,056 | 6 | Worm riding |

Three hardware variants (non-HSQ):
- `.AGD` — Tandy/PCjr
- `.M32` — Roland MT-32/LAPC-I MIDI

Reference: `tools/herad_decoder.py` (analysis + MIDI export via `--midi DIR`)

---

## DUNE.DAT (Archive)

Indexed archive containing all game resources. Files can be overridden by placing
loose files in the game directory.

---

## DS Variable Map (Data Segment)

Key game state variables referenced by CONDIT/DIALOGUE bytecodes via DS offsets.
Base address: DS:0x1138. Full map in `lib/constants.py`.

Selected variables:
```
Offset  Name                 Size  Description
0x2A    GameStage            byte  Master story progression
0x1A    CharismaLevel        byte  Paul's charisma
0x44    GameElapsedTime      word  Day/hour packed
0x4D    SpiceLevel           word  Spice stockpile
0x49    ContactFlag          byte  Sietch contact status
0x1B    ArmyScore            byte  Military strength
0x1C    EcologyScore         byte  Ecology progress
0x57    WindtrapCount         byte  Windtrap installations
0x80    SietchStatusArray    array Per-sietch flags
```

---

## Tool Reference

| Tool | Formats | Description |
|------|---------|-------------|
| `tools/hsq_decompress.py` | HSQ | Decompress any HSQ file |
| `tools/save_editor.py` | DUNE*.SAV | Read/write save files |
| `tools/condit_decompiler.py` | CONDIT.HSQ | Decompile condition bytecodes |
| `tools/condit_recompiler.py` | CONDIT.HSQ | Recompile expressions to bytecodes |
| `tools/dialogue_decompiler.py` | DIALOGUE.HSQ | Decompile dialogue bytecodes |
| `tools/dialogue_browser.py` | CONDIT+DIALOGUE+PHRASE | Cross-reference dialogue pipeline |
| `tools/phrase_dumper.py` | PHRASE*.HSQ | Dump dialogue text strings |
| `tools/command_decoder.py` | COMMAND*.HSQ | Decode UI string tables |
| `tools/sprite_decoder.py` | 133 sprite HSQ files | Decode/export sprite graphics |
| `tools/map_decoder.py` | MAP.HSQ | Analyze world map terrain |
| `tools/sal_decoder.py` | *.SAL | Decode scene assembly layouts |
| `tools/bin_decoder.py` | *.BIN | Decode binary data files |
| `tools/hnm_decoder.py` | *.HNM | Analyze HNM video files |
| `tools/lop_decoder.py` | *.LOP | Decode loop animations |
| `tools/herad_decoder.py` | HERAD music HSQ | Decode music + MIDI export |
| `tools/sound_decoder.py` | SN*.HSQ | Decode VOC sounds + WAV export |
| `tools/npc_smuggler_decoder.py` | DUNE*.SAV | Decode NPC/smuggler data |
| `tools/file_index.py` | All | Classify all 262 game files |
