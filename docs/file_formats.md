# Dune 1992 Game Resource Formats

## HSQ Compression

LZ77-variant used for most game resources (`.HSQ` extension).

### Header (6 bytes)
```
Offset  Size  Field
0x00    2     Decompressed size (uint16 LE)
0x02    2     Compressed size (uint16 LE)
0x04    2     Checksum (uint16 LE, ignored)
```

### Bitstream Decoder
- Bit 1: literal byte follows
- Bit 0 + bit 1: short back-reference (2 bytes: offset + length)
- Bit 0 + bit 0: long back-reference (2-3 bytes: offset + length)
  - Length 0, offset 0 = EOF
  - Length 0, offset != 0 = length in next byte + 1

## SAL (Scene Assembly Language)

Room layout format used by sietch interiors (`*.SAL`).

### Structure
```
Offset table: N × uint16 LE (N = first_offset / 2)
Section data: FF FF terminated bytecodes per section
```

### Command Types
1. **Sprite**: `sprite_id > 0x01, !(mod & 0x80)` → 5 bytes
2. **Marker**: `sprite_id == 0x01` → 5 bytes (navigation hotspots, NPC positions)
3. **Polygon**: `mod & 0x80, !(mod & 0x40)` → variable (12-bit vertex coords)
4. **Line**: `mod & 0x80, mod & 0x40` → 10 bytes

Source: OpenRakis `dunesal.c`

## HNM4 (Video)

Cryo Interactive proprietary video format (`*.HNM`).

- Resolution: 320×152 pixels
- Frame offset table in header
- Chunk types: `PL` (palette), `SD` (sound), `VD` (video delta)

## LOP (Loop Animation)

Ambient animation loops referencing HNM keyframes (`*.LOP`).

- Shares frame offset format with HNM
- Delta encoding: `F8 FF FF` = copy tile, `55 55` = marker

## HERAD (Music)

Cryo's proprietary music format. Three hardware variants:
- `.HSQ` — OPL2/AdLib/Sound Blaster
- `.AGD` — Tandy/PCjr
- `.M32` — Roland MT-32/LAPC-I MIDI

## DUNE.DAT (Archive)

Indexed archive containing all game resources. Files can be overridden by placing loose files in the game directory.
