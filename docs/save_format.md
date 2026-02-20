# Dune 1992 Save File Format (CD v3.7)

## Overview

Save files (`DUNE*.SAV`) are F7 RLE compressed. Typical size: ~13KB compressed → ~22KB decompressed.

All offsets below are into the **decompressed** data (0-indexed).

> **Note**: DuneEdit2 uses 1-indexed offsets. Subtract 1 to convert to our 0-indexed system.

## F7 RLE Compression

| Pattern | Meaning |
|---------|---------|
| `F7 01 F7` | Literal byte 0xF7 |
| `F7 NN VV` (NN > 2) | Repeat byte VV exactly NN times |
| Any other byte | Literal |

Source: DuneEdit2 `SequenceParser.cs` / `SaveGameFile.cs`

## Complete Offset Map

```
Offset    Size    Field
--------  ------  --------------------------------------------------
0x0000    ~17KB   Screen/graphics data (F7 RLE compressed framebuffer)
0x3338    ???     Dialogue state (runtime copy of DIALOGUE.HSQ state)
0x441E    ???     Time counters block
0x4446    1       Number of Rallied Troops (uint8)
0x4447    1       Charisma (uint8, GUI displays value / 2)
0x4448    1       ★ GameStage ★ (uint8, 0x00-0xC8, master progression)
0x44BE    2       Spice stockpile (uint16 LE, ×10 = displayed kg)
0x451E    1960    Sietch block: 70 × 28 bytes
0x4CC6    2       Troop sentinel (FF FF)
0x4CC8    1836    Troop block: 68 × 27 bytes
0x53F4    ???     NPC data block (~16 bytes per record)
0x54F6    ???     Smuggler data
0x5592    2       DateTime (uint16 LE)
0x5594    1       Contact Distance (uint8)
```

## DateTime Encoding

```
GameElapsedTime (uint16 LE at offset 0x5592):
  Bits 0-3:   Hour of day (0-15) — 16-hour Arrakis day cycle
  Bits 4-15:  Day number (0-4095)

  hour = value & 0xF
  day  = value >> 4
  sunlight_day = (value + 3) >> 4
```

Source: Cryogenic `TimeCode.cs`, DNCDPRG.EXE `sub_1AD1` / `sub_1AE0`

## GameStage Values

| Value | Name | Description |
|-------|------|-------------|
| 0x00 | Start | Intro sequence |
| 0x01 | MetGurney | Met Gurney Halleck |
| 0x04 | FindProspectors | Tasked to find spice prospectors |
| 0x08 | ProspectorsFound | Located prospector sietches |
| 0x0C | FoundComms | Found communications equipment |
| 0x10 | FoundHarvester | Located harvester |
| 0x14 | PostHarvester | After harvester acquisition |
| 0x18 | EcologyIntro | Introduced to ecology |
| 0x1C | WaterDiscovery | Discovered water sources |
| 0x20 | MidGame | Mid-game phase |
| 0x24 | SietchTuek | Sietch Tuek events |
| 0x28 | PreStilgar | Before meeting Stilgar |
| 0x2C | TakeStilgar | Taking Stilgar's sietch |
| 0x30 | PostStilgar | After Stilgar events |
| 0x35 | LetoLeft | Duke Leto departed |
| 0x38 | HarkonnenPush | Harkonnen offensive |
| 0x3C | Resistance | Fremen resistance phase |
| 0x40 | CounterAttack | Counter-attack phase |
| 0x48 | PreWorm | Before worm riding |
| 0x4F | CanWormRide | Worm riding unlocked |
| 0x50 | RodeWorm | First worm ride completed |
| 0x58 | ArmyBuilding | Building the army |
| 0x60 | FindChani | Finding Chani |
| 0x64 | ChaniKidnapped | Chani kidnapped event |
| 0x68 | ChaniReturned | Chani returned |
| 0xC8 | Ending | Victory / end game |

## Troop Record (27 bytes)

68 records starting at offset 0x4CC8.

```
Offset  Size  Field
------  ----  -----
+0x00   1     Troop ID
+0x01   1     Next troop in location (linked list)
+0x02   1     Position around location
+0x03   1     Job code (see below)
+0x04   1     Unknown
+0x05   1     Sietch ID (location assignment)
+0x06   1     Unknown
+0x07   1     Unknown
+0x08   1     Spice mining skill (0-255)
+0x09   1     Army/combat skill (0-255)
+0x0A   1     Ecology skill (0-255)
+0x0B   1     Equipment bitfield
+0x0C   2     Population (uint16 LE)
+0x0E   1     Motivation (0-255)
+0x0F   1     Spice mining rate
+0x10-0x18    Unknown fields
+0x19   1     Dissatisfaction (0-255)
+0x1A   1     Unknown
```

### Job Codes

| Value | Job |
|-------|-----|
| 0 | None/Idle |
| 1 | Spice Mining |
| 2 | Spice Mining (alt) |
| 3 | Military Training |
| 4 | Military (Army) |
| 5 | Ecology (Vegetation) |
| 6 | Equipment Manufacturing |
| 7 | Spice Prospecting |
| 8 | Espionage |

### Equipment Bitfield

| Bit | Equipment |
|-----|-----------|
| 0x01 | Knives |
| 0x02 | Krysknives |
| 0x04 | Laser Guns |
| 0x08 | Weirding Modules |
| 0x10 | Atomics |
| 0x20 | Bulbs |
| 0x40 | Harvesters |
| 0x80 | Ornithopters |

## Sietch Record (28 bytes)

70 records starting at offset 0x451E.

```
Offset  Size  Field
------  ----  -----
+0x00   1     Status bitfield
+0x01   1     Unknown
+0x02   2     GPS X coordinate (uint16 LE)
+0x04   2     GPS Y coordinate (uint16 LE)
+0x06   1     Region/type
+0x07   1     Housed troop ID
+0x08   1     Spice density
+0x09-0x18    Unknown fields
+0x19   1     Equipment bitfield (same as troop)
+0x1A   1     Water level (0-255)
+0x1B   1     Spice amount (0-255)
```

### Status Bitfield

| Bit | Meaning |
|-----|---------|
| 0x01 | Discovered |
| 0x02 | Visited |
| 0x04 | Has vegetation |
| 0x08 | In battle |
