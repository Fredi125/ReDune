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
6 files: SN1-SN4, SN6, SNA. Header starts with `"Creative Voice File"`.

---

## FREQ.HSQ (Frequency Sample)

Sound frequency calibration sample. Starts with `"Sample test to calc freq"`.

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

## HNM4 (Video)

Cryo Interactive proprietary video format (`*.HNM`).

- Resolution: 320×152 pixels
- Frame offset table in header
- Chunk types: `PL` (palette), `SD` (sound), `VD` (video delta)

---

## LOP (Loop Animation)

Ambient animation loops for location backgrounds (`*.LOP`). 6 files.

### Header (24 bytes)
```
uint16 LE:  header size (always 0x0018 = 24)
uint16 LE:  marker (always 0xFFFF)
5 × uint32 LE:  section offsets (4 frame sections + end)
```

### Sections
- **Sections 0-2**: Animation frame data (~8-15 KB each)
- **Section 3**: Metadata block (always 24 bytes, animation parameters)

### Files
| File | Size | Description |
|------|------|-------------|
| MNT1.LOP | 38,315 | Mountain pass 1 |
| MNT2.LOP | 38,331 | Mountain pass 2 |
| MNT3.LOP | 58,419 | Mountain pass 3 |
| MNT4.LOP | 58,189 | Mountain pass 4 |
| PALACE.LOP | 34,965 | Palace exterior |
| SIET.LOP | 35,616 | Sietch exterior |

---

## HERAD (Music)

Cryo's proprietary OPL2/AdLib music format.

### Header
```
uint16 LE at offset 0:  file size
bytes 2-3:              0x32 0x00 (HERAD signature = 50)
remaining header:       track offset table (uint16 LE pairs)
```

10 HERAD files in game data: ARRAKIS, BAGDAD, CRYOMUS, MORNING, SEKENCE,
SIETCHM, WARSONG, WATER, WORMINTR, WORMSUIT.

Three hardware variants (non-HSQ):
- `.AGD` — Tandy/PCjr
- `.M32` — Roland MT-32/LAPC-I MIDI

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
