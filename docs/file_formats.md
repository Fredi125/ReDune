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

## DIALOGUE.HSQ (Dialogue Script Table)

Dialogue script table controlling NPC conversations. **Not a bytecode VM** — it uses
fixed 4-byte records that reference CONDIT conditions and PHRASE text strings.

4,496 bytes decompressed. 136 entries, 988 records total, 480 unique phrase IDs.

### Structure
```
Offset table:  136 × uint16 LE → dialogue entry offsets (N = first_offset / 2)
Data region:   Lists of 4-byte records, each terminated by 0xFFFF
```

### Record Format (4 bytes)
```
Byte 0: Flags + Action Code
  Bit 7 (0x80): "Already spoken" flag (set at runtime, persisted in save)
  Bit 6 (0x40): "Repeatable" — can be shown again after being spoken
  Bits 5-4:     Additional flags (0x20, 0x10 observed)
  Bits 3-0:     NPC action code (0-15, index into CS:0xA107 jump table)

Byte 1: NPC/Character ID
  Low byte of the CONDIT condition index

Byte 2: Condition type + Menu flag + Phrase ID (high)
  Bits 7-6: Condition type (0-3):
    0 = unconditional (always show)
    1 = check CONDIT[256 + byte1]
    2 = check CONDIT[512 + byte1]
    3 = (not observed)
  Bits 3-2: Menu option flag (nonzero → clickable dialogue choice)
  Bits 1-0: High 2 bits of 10-bit phrase ID

Byte 3: Phrase ID (low byte)
  Full phrase ID = ((byte2 & 0x03) << 8) | byte3
  Looked up in PHRASE*.HSQ with 0x800 OR-mask
```

### CONDIT Integration

Full CONDIT index = `(condition_type × 256) + byte1`:
- Type 0 → indices 0-255 (unconditional, 462 records)
- Type 1 → indices 256-511 (conditional, 324 records)
- Type 2 → indices 512-712 (conditional, 202 records)

This maps exactly to CONDIT.HSQ's 713 entry offset table.

### Processing Logic (sub_19F9E)

1. Read 4-byte records until `0xFFFF` terminator
2. Check "already spoken" (bit 7): if set and not repeatable (bit 6), skip
3. Evaluate CONDIT condition: if FALSE, skip
4. Call action function from bits 3-0 (if nonzero)
5. If menu flag (bits 3-2 of byte 2) set, add to dialogue menu
6. Set "spoken" bit (byte 0 |= 0x80)
7. Display phrase text

### Save File Mapping

Dialogue state persisted at save offset **0x3338**. Only byte 0 of records changes
at runtime (bit 7 gets set when lines are spoken).

Reference: `tools/dialogue_decompiler.py`, `tools/dialogue_browser.py`

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

16,091 bytes decompressed. Dual-purpose data resource containing polygon
shading tables and globe projection mappings.

### Part 1: Gradient Tables (0x0000-0x0B34, 2869 bytes)

55 variable-length gradient tables for polygon shading fills.

```
Table format:
  Byte 0:     Marker byte (table length = 256 - marker)
  Bytes 1-N:  Incrementing color indices (gradient ramp)
```

Marker range: 0xBF-0xF1 (table sizes 14-64 entries). Base colors 0x00-0x56.
Terminated by 0xFF sentinel bytes.

Used by `_sub_13BE9_SAL_polygon` for shaded polygon fills in SAL scenes.
The polygon renderer selects a table by color, then indexes into it by
shade level to produce smooth gradient-filled regions.

### Part 2: Globe Projection (0x0B35-0x3EDA, 13222 bytes)

Globe latitude scanline data for the spinning world map view.

```
Layout:
  0x0B35-0x0CDA:  422 bytes zero prefix (padding)
  0x0CDB-0x3EDA:  64 × 200-byte scanline blocks
```

Each 200-byte block represents one latitude line (equator to pole;
the other hemisphere is mirrored):

```
Block structure (200 bytes):
  Bytes 0-97:   98-byte longitude ramp (x → longitude coordinate mapping)
  Byte 98:      0x00 separator
  Bytes 99-199: 101-byte terrain/shade data (99 values + 2 zero padding)
```

**Longitude ramp**: Maps screen x-pixel positions to globe longitude
coordinates. At the equator (block 0), the mapping is linear (02, 04, 06,
..., C4). At higher latitudes, values advance non-linearly due to sphere
curvature, and the maximum longitude decreases (0xC4 at equator → 0x0E
at pole).

**Terrain data**: Shade/terrain type indices for each longitude position
at this latitude, looked up during rendering to determine pixel colors
(cross-referenced with the gradient tables from Part 1).

### Buffer Reuse

At runtime, `RESOURCE_GLOBDATA` is also used for map terrain histograms
(256 × uint16 LE counting byte values in MAP.HSQ), overwriting the
loaded file content. This histogram is used for sietch terrain frequency
calculations.

### Related ASM Functions
- `sub_1B8A7`: loads GLOBDATA.HSQ (resource index 0x92)
- `sub_1BA75`: globe rendering setup (latitude calculations)
- `gfx_vtable_func_29`: VGA driver globe rendering (called with TABLAT + GLOBDATA + MAP)
- `_sub_13BE9_SAL_polygon`: polygon shading using gradient tables

Reference: `tools/globdata_decoder.py`

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
10 files: 6 HSQ-compressed (SN1-SN4, SN6, SNA), 4 uncompressed (SN5, SN7-SN9).

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
- `codec`: 0x00 = 8-bit unsigned PCM, 0x01 = 4-bit Creative ADPCM
- Sample data: `length - 2` bytes

### Sound Effects

| File | Rate (Hz) | Duration | Blocks | Codec | Description |
|------|-----------|----------|--------|-------|-------------|
| SN1.HSQ | 10,416 | 1.82s | 3 (repeat ∞) | PCM8 | Worm / sandstorm |
| SN2.HSQ | 12,658 | 1.54s | 1 | PCM8 | Ornithopter engine |
| SN3.HSQ | 6,756 | 2.91s | 1 (repeat ∞) | PCM8 | Spice harvester |
| SN4.HSQ | 14,285 | 0.65s | 1 | PCM8 | Click/beep |
| SN5.VOC | 5,025 | 3.91s | 1 (repeat ∞) | PCM8 | Wind / ambient |
| SN6.HSQ | 8,928 | 2.34s | 2 (repeat 30+5) | PCM8 | Multi-part effect |
| SN7.VOC | 8,928 | 1.52s | 2 (repeat 10) | ADPCM | Rhythmic effect |
| SN8.VOC | 4,000 | 4.94s | 2 (repeat 10) | PCM8 | Deep rumble |
| SN9.VOC | 7,407 | 0.55s | 1 | PCM8 | Short burst |
| SNA.HSQ | 7,692 | 2.48s | 2 (repeat ∞) | PCM8 | Ambient sound |

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
| HERAD Music | 30 | Music tracks (10 × 3 variants: HSQ/AGD/M32) |
| x86 Drivers | 10 | Hardware driver overlays |
| String Tables | 7 | UI text (7 language variants) |
| Creative Voice | 6 | VOC sound effects |
| Map Data | 3 | World map, globe data |
| VM Bytecodes | 2 | CONDIT conditions, DIALOGUE triggers |
| Sound Sample | 1 | Frequency calibration |

---

## HNM (Video)

Cryo Interactive proprietary video format (HNM version 1, `*.HNM`). 36 files
used for intro, cutscenes, location transitions, and ending sequence.

### File Structure

Chunk-based format. All multi-byte values are little-endian.

**Chunk 0 (header)**:
```
uint16 LE: headerSize (total size of header chunk)
Palette blocks:
  Series of uint16 LE entries:
    0xFFFF     → end of palette data
    0x0100     → skip 3 bytes (padding)
    Other      → low byte = start index, high byte = count (0→256)
                 followed by count × 3 bytes of 6-bit VGA RGB
0xFF fill bytes (variable, skip until non-0xFF)
Frame offset table:
  N+1 × uint32 LE (offsets relative to headerSize)
  N = (headerSize - table_position) / 4 - 1
```

**Subsequent chunks (AV frames)**:
```
uint16 LE: avFrameSize (matches frame offset delta)
Sub-chunks (tagged, processed sequentially):
```

### Sub-chunk Tags

| Tag (uint16 LE) | ASCII | Data | Description |
|-----------------|-------|------|-------------|
| 0x6C70 | `pl` | uint16 size + palette block | Palette update |
| 0x6473 | `sd` | uint16 size + PCM samples | Audio data (8-bit unsigned, 11111 Hz) |
| 0x6D6D | `mm` | uint16 size + data | Metadata (unused) |
| Other | — | 4-byte frame header + pixel data | Video frame |

### Video Frame Header (4 bytes)

When a sub-chunk tag doesn't match known tags, the tag's 2 bytes are the first
2 bytes of the frame header:

```
Byte 0: width low 8 bits
Byte 1: bit 0 = width bit 8, bits 1-7 = flags
Byte 2: height
Byte 3: mode
```

**Width**: `((byte1 & 0x01) << 8) | byte0` (9-bit, max 511)

**Flags** (`byte1 & 0xFE`):
- `0x02`: HSQ-compressed data follows (6-byte compression header)
- `0x04`: full frame (no x,y offset in decompressed data)
- `0x80`: PackBits-compressed pixel rendering

**Mode**:
- `0xFE`: opaque copy (all pixels written)
- `0xFF`: transparent (pixel value 0 = skip/transparent)

### Frame Decompression

If `flags & 0x02`, a 6-byte compression header follows the frame header:
```
uint16 LE: decompressed size
uint8:     zero (must be 0x00)
uint16 LE: compressed size
uint8:     salt (checksum byte)
```

Dispatch by sum of all 6 header bytes:
- **0xAB** (171): Standard HSQ/LZ77 (same algorithm as file-level HSQ)
- **0xAD** (173): AD codec with codebook and bitstream RLE

After decompression (or if uncompressed):
- If `flags & 0x04 == 0`: first 4 bytes = x_offset (uint16 LE) + y_offset (uint16 LE)
- Remaining data = pixel data rendered to 320×200 frame buffer

### PackBits Rendering (`flags & 0x80`)

Per scanline (width pixels):
- `cmd & 0x80`: RLE — repeat next byte `(257 - cmd)` times
- Else: literal — copy `(cmd + 1)` bytes

### AD Codec (Checksum 0xAD)

Advanced compression using codebook + bitstream RLE. Header reinterpretation:
```
uint16 LE: framesize (decompressed pixel data size)
uint16 LE: codebooksize
uint8:     flags (0x04=full frame, 0x40=color base 0x80, 0x80=alternate mode)
uint8:     salt
```

**Codebook unpacking**: LZ-like back-references with 4-bit packed lengths.
**Pixel decoding**: Bitstream-driven with 1×, 2×, 3×, 4×, and extended RLE modes.

### Video Files (36 total)

| Category | Files | Resolution | Audio | Description |
|----------|-------|------------|-------|-------------|
| Intro sequences | SEQ[ABDDGIJKMNPQR] | 160×95 | Yes | Cutscene videos with dialogue |
| Cryo logo | CRYO, CRYO2 | 320×139-200 | No | Publisher splash screens |
| Virgin logo | VIRGIN | 320×200 | No | Publisher animation |
| Title | TITLE, PRESENT | 320×200 | No | Title sequence, zoom effects |
| Locations | MTG1-3, MNT1-4, FORT, SIET, PALACE, PLANT, VER | 320×152 | No | Location background animations |
| Death scenes | DEAD, DEAD2, DEAD3 | 320×152 | No | Game over screens |
| Ending | DFL2, IRULAN | 320×152, 160×91 | IRULAN only | Ending sequence |
| Credits | CREDITS, AABBBBB | 320×152 | No | Credits roll |

All 36 files use LZ codec (0xAB). No AD codec (0xAD) observed in CD v3.7 files.

Reference: `tools/hnm_decoder.py` (analysis, BMP frame export, WAV audio extraction),
OpenRakis `HNMExtractor.cpp`, ScummVM `video.cpp`

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

Cryo's proprietary music format ("Hérault") with three hardware variants:
- **HSQ** (OPL2/AdLib): 9 tracks, fixed status bytes, FM synthesis instruments
- **AGD** (Tandy/PCjr): same as HSQ + 32-byte extra header for channel config
- **M32** (Roland MT-32): single track with standard MIDI channelized events

Each of the 10 music tracks exists in all 3 variants (30 total files).

### Common Header (bytes 0x00-0x31, all variants)
```
Offset  Size  Field
0x00    2     Instrument block offset (uint16 LE)
0x02    2     Track 0 offset (signature: 0x0032 for HSQ/M32, 0x0052 for AGD)
0x04    2+    Track 1..N offsets (uint16 LE, 0x0000 = end)
...           Zero padding to 0x2C
0x2C    2     Number of instruments (uint16 LE)
0x2E    2     Param2 — tempo/speed related (uint16 LE)
0x30    2     Param3 — loop count (uint16 LE)
```

**Identification**: Word at offset 2 is `0x0032` (HSQ/M32) or `0x0052` (AGD).
Exception: `CRYOMUS.AGD` uses `0x0032` (identical header to HSQ variant).

### AGD Extra Header (bytes 0x32-0x51, AGD only)

When signature = `0x0052`, 32 extra bytes at 0x32-0x51 contain Tandy/PCjr-specific
channel configuration. Track data starts at 0x52 instead of 0x32. All track offsets
in the header are shifted +0x20 relative to HSQ. Some AGD files have more tracks
than their HSQ counterparts (e.g., WORMINTR: 13 tracks vs 9, WORMSUIT: 15 vs 9).

### Track Data (offset data_start to instrument_offset)

Each track begins with a 2-byte header:
- Byte 0: initial delay (single byte, typically 0x00-0x7F)
- Byte 1: voice assignment (0x04 on track 0, 0xFF on tracks 1-8)

### Event Stream — HSQ/AGD (OPL2, no channel in status byte)

| Status | Name | Data | Description |
|--------|------|------|-------------|
| 0x90 | Note On | note, velocity | Start playing note |
| 0x80 | Note Off | note, velocity | Stop playing note |
| 0xC0 | Program Change | instrument | Select OPL2 instrument |
| 0xD0 | Control | param, value | Parameter change |
| 0xFF | Voice/Sync | — | Channel marker |

### Event Stream — M32 (standard MIDI channelized)

| Status | Name | Data | Description |
|--------|------|------|-------------|
| 0x9N | Note On | note, velocity | Note on, channel N |
| 0x8N | Note Off | note, velocity | Note off, channel N |
| 0xBN | Control Change | cc, value | Control change, channel N |
| 0xCN | Program Change | program | Patch select, channel N |
| 0xEN | Pitch Bend | LSB, MSB | Pitch wheel, channel N |
| 0xDN | Aftertouch | pressure | Channel pressure, channel N |

M32 files always have 1 track containing a multiplexed stream across up to 8 MIDI
channels. Note counts are typically higher than OPL2 (e.g., ARRAKIS: 7,182 M32
notes vs 3,637 OPL2 — the Roland arrangement is more detailed).

### Delta Time Encoding (all variants)

If next byte is a status byte (>= 0x80), implicit delta = 0. Otherwise, read
VLQ-encoded delta time before the status byte. VLQ uses standard MIDI bit-7
continuation encoding.

### Instrument Definitions (at instrument_offset)

OPL2/FM synthesis register data, 11+ bytes per instrument:
modulator registers, carrier registers, feedback/connection byte.
M32 files contain MT-32 patch definitions instead.

### Music Files — OPL2/AdLib (HSQ)

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

### Variant Comparison

| Track | HSQ Notes | AGD Notes | AGD Tracks | M32 Notes | M32 Channels |
|-------|-----------|-----------|------------|-----------|--------------|
| ARRAKIS | 3,637 | 3,637 | 9 | 7,182 | 8 |
| BAGDAD | 3,954 | 3,954 | 9 | 5,916 | 8 |
| CRYOMUS | 308 | 308 | 9 | 532 | 4 |
| MORNING | 3,466 | 3,466 | 9 | 5,744 | 7 |
| SEKENCE | 3,656 | 3,656 | 9 | 5,924 | 8 |
| SIETCHM | 2,254 | 2,254 | 9 | 3,768 | 6 |
| WARSONG | 2,748 | 2,748 | 9 | 4,492 | 7 |
| WATER | 2,788 | 2,788 | 9 | 5,016 | 7 |
| WORMINTR | 1,766 | 1,766 | 13 | 2,668 | 7 |
| WORMSUIT | 4,056 | 4,056 | 15 | 6,988 | 8 |

Reference: `tools/herad_decoder.py` (analysis + MIDI export via `--midi DIR`)

---

## DUNE.DAT (Archive)

Main game archive containing all resources. 2549 files including subdirectory
paths for voice files. Files can be overridden by placing loose files in the
game directory.

### Header (64KB = 0x10000)
```
Offset  Size  Field
0x00    2     File count hint (uint16 LE, 0x0A3D = 2621 for CD v3.7)
0x02    25×N  File entry records (25 bytes each)
...           Zero-padded to 0x10000
```

**Version/magic**: The first uint16 `{0x3D, 0x0A}` serves as both file count
hint (used by ScummVM for `reserve()`) and version magic (checked by DuneExtractor).

### File Entry (25 bytes)
```
Offset  Size  Field
+0x00   16    Filename (null-padded ASCII, may include "\" subdirectory paths)
+0x10   4     File size (int32 LE)
+0x14   4     File offset (int32 LE, absolute from archive start)
+0x18   1     Flag (unused in CD version, always 0x00)
```

Entry list terminates when `name[0] == 0x00`.

### Data Region (starts at 0x10000)

File data stored at offsets specified in the header entries. HSQ-compressed files
are auto-detected by the 6-byte header checksum (sum ≡ 0xAB mod 256).

### Archive Contents (CD v3.7)

| Category | Count | Description |
|----------|-------|-------------|
| Voice files (VOC) | ~2300 | Character dialogue (PA\, PB\, etc. subdirs) |
| Sprite graphics | 133 | Portraits, backgrounds, UI |
| HNM video | 36 | Cutscenes, animations |
| HERAD music | 30 | Music (10 tracks × HSQ/AGD/M32) |
| SAL scenes | 4 | Room layouts |
| LOP animations | 6 | Ambient loops |
| Game data | ~30 | BIN, MAP, CONDIT, DIALOGUE, COMMAND |
| x86 drivers | 10 | Hardware driver overlays |

Reference: `tools/dat_decoder.py`, ScummVM `archive.cpp`, OpenRakis `DuneExtractor.cs`

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
| `tools/hnm_decoder.py` | *.HNM | Decode HNM video + BMP/WAV export |
| `tools/dat_decoder.py` | DUNE.DAT | List/extract archive contents |
| `tools/lop_decoder.py` | *.LOP | Decode loop animations |
| `tools/herad_decoder.py` | HERAD music (HSQ/AGD/M32) | Decode all 3 variants + MIDI export |
| `tools/sound_decoder.py` | SN*.HSQ | Decode VOC sounds + WAV export |
| `tools/npc_smuggler_decoder.py` | DUNE*.SAV | Decode NPC/smuggler data |
| `tools/file_index.py` | All | Classify all 262 game files |
