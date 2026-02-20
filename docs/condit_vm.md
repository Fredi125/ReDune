# CONDIT VM Architecture

## Overview

CONDIT.HSQ contains a bytecode-driven condition evaluator that gates dialogue options and event triggers. It's a stack-based expression evaluator decoded from three functions in DNCDPRG.EXE.

## Source Functions (DNCDPRG.EXE)

| Address | Name | Purpose |
|---------|------|---------|
| CS1:0xC266 | `sub_C266` | Main evaluator loop |
| CS1:0xC1DB | `sub_C1DB` | Operand reader (variables/immediates) |
| CS1:0xC204 | `sub_C204` | Operation dispatcher (10-entry jump table) |

## File Structure

```
CONDIT.HSQ: 10,907 bytes decompressed (5,618 compressed)

Offset table: 713 × uint16 LE = 1,426 bytes
  Entry 0 offset at byte 0
  Entry 1 offset at byte 2
  ...
  Entry 712 offset at byte 1424

Bytecode area: starts at offset 0x0592 (1,426)
  41 bytecode chains with 713 entry points
  342 empty/padding entries (all zeros)
  371 non-empty entries
```

## Key Discovery: Shared Bytecode Chains

The 713 offset-table entries do NOT point to 713 independent conditions. They point into **41 shared bytecode chains**. Multiple entries can share the same chain by entering at different offsets, evaluating different subsets of the chain's conditions.

Example: Entries 2-6 all terminate at the same 0xFF byte at offset 0x05F5. Entry 2 starts earliest (evaluating the most conditions), while entry 6 starts latest (evaluating the fewest).

## Operand Encoding (sub_C1DB)

```
Type byte → decoding:

01 XX       → byte variable at DS:[XX]    (read as uint8)
00 XX       → word variable at DS:[XX]    (read as uint16 LE)
02-7F XX    → word variable at DS:[XX]    (type byte distinguishes size)
80 XX       → immediate byte value XX
81-FF XXXX  → immediate word value XXXX   (uint16 LE)
```

### Key Variables

| DS Offset | Type | Name | Save Offset | CONDIT Refs |
|-----------|------|------|-------------|-------------|
| 0x002A | byte | GameStage | 0x4448 | 70+ |
| 0x0002 | uint16 | GameElapsedTime | 0x5592 | ~15 |
| 0x00FC | byte | var_FC | unknown | ~30 |

## Operation Codes (off_C246 Jump Table)

Extracted from the jump table at `off_C246` in DNCDPRG.ASM:

```
BL & 0x1F → operation index:

  0x00: EQ   dx == ax → 0xFFFF, else 0     (equality)
  0x01: LT   dx < ax  → 0xFFFF, else 0     (unsigned less-than)
  0x02: GT   dx > ax  → 0xFFFF, else 0     (unsigned greater-than)
  0x03: NE   dx != ax → 0xFFFF, else 0     (not-equal)
  0x04: LE   dx <= ax → 0xFFFF, else 0     (signed less-or-equal)
  0x05: GE   dx >= ax → 0xFFFF, else 0     (signed greater-or-equal)
  0x06: ADD  dx = dx + ax                   (addition)
  0x07: SUB  dx = dx - ax                   (subtraction)
  0x08: AND  dx = dx & ax                   (bitwise AND)
  0x09: OR   dx = dx | ax                   (bitwise OR)
  0x0A-0x0F: NOP  dx = 0                    (unused)
```

Comparisons return 0xFFFF (true) or 0x0000 (false).

## Execution Model (sub_C266)

### Bytecode Structure

```
<operand1> [<op> <operand2>]* [<separator> <operand1> [<op> <operand2>]*]* FF
```

### Control Bytes

| Range | Meaning |
|-------|---------|
| 0x00-0x7F | Inline operation: `op_index = byte & 0x1F`, apply immediately |
| 0x80-0xFE | Separator: push `(accumulator, byte & 0x1F)` to stack, start new sub-expression |
| 0xFF | Terminator: unwind stack, return result |

### Execution Algorithm

```
1. Read first operand → DX (accumulator)

2. Loop:
   a. Read next byte
   b. If byte == 0xFF → break (done)
   c. If byte < 0x80:
      - op_index = byte & 0x1F
      - Read operand → AX
      - DX = operation[op_index](DX, AX)
   d. If byte >= 0x80:
      - deferred_op = byte & 0x1F
      - Push (DX, deferred_op) to stack
      - Read new operand → DX (start sub-expression)

3. Unwind stack:
   For each (saved_value, op) popped from stack:
     DX = operation[op](saved_value, DX)

4. Return:
   DX != 0 → condition is TRUE (event/dialogue available)
   DX == 0 → condition is FALSE (event/dialogue blocked)
```

## Examples

### Entry 0: Simple Variable Test
```
Raw:       01 FC FF
Decoded:   byte[var_FC]
Meaning:   Return TRUE if var_FC is non-zero
```

### Entry 1: GameStage Check with Nested Condition
```
Raw:       01 2A 00 80 01 90 02 10 12 02 12 10 80 10 00 80 00 FF
Decoded:   (byte[GameStage] == 0x01) ?16 (word[0x10] ?18 word[0x12] ?16 0x10 == 0x00)

Breakdown:
  01 2A          → byte[GameStage] (first operand)
  00 80 01       → operation 0x00 (EQ), immediate 0x01
                   Result: GameStage == 1 (MetGurney)?
  90             → separator! Push (result, op 0x10) to stack
  02 10          → word[DS:0x10] (new sub-expression)
  12             → operation 0x12 → 0x12 & 0x1F = 0x12... 
                   (this is actually op + next operand encoding)
  ...
  FF             → terminate, unwind stack
```

### Entry 27: Two-Variable Expression
```
Raw:       26 08 2A 01 FC FF
Decoded:   word[0x08] ?10 byte[var_FC]

Breakdown:
  26 08          → word[DS:0x08] (first operand, type_byte=0x26)
  2A             → separator! Push (word[0x08], op 0x0A = OR) to stack
  01 FC          → byte[var_FC] (new sub-expression)
  FF             → terminate, unwind: word[0x08] OR byte[var_FC]
```

## Runtime Integration

```
CONDIT loaded at:     DS:0xAA72 (segment:offset pointer)
Dialogue evaluator:   Calls sub_C266 with 1-based condition index
Variable reads:       From DS segment (game state memory)
Condition result:     Gates whether dialogue option appears / event triggers
```

The game's dialogue system uses CONDIT indices to check preconditions before showing conversation options. When a CONDIT entry evaluates to TRUE, the corresponding dialogue node or event becomes available.
