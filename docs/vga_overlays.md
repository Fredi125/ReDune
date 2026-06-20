# Dune 1992 — VGA rendering overlays (`DN386.HSQ` / `DNVGA.HSQ`)

`DNCDPRG.EXE` (the published `OpenRakis/asm/cd/DNCDPRG.ASM`) is **loader + CONDIT
VM + HSQ decompressor only** — it has *no* VGA palette, framebuffer, globe or
sprite code (verified: zero `3C8h`/`3C9h`, zero `0A000h`). The actual rendering
lives in two HSQ-compressed real-mode overlays:

| Overlay | Role | Decompressed |
|---------|------|--------------|
| `DN386.HSQ` | 386 main VGA renderer | 15010 B |
| `DNVGA.HSQ` | generic-VGA twin (same structure, offsets shifted a few bytes) | 14998 B |

They are **pure rendering drivers**: a jump-table blit/fill/clear/scale ABI plus
palette and a couple of screen-effect routines. The higher-level *game logic*
(which cel to draw, the globe's longitude origin, scene scripting) lives in a
separate segment the project calls **"CS1"** (e.g. `calc_SAL_index@CS1:0x5E4F`,
the globe caller `sub_1BA75` — offsets > 64 KB that fit neither DNCDPRG nor these
15 KB overlays), which has **not** been disassembled here.

Decompress + disassemble (objdump does 16-bit x86 faithfully — verified against
hand-decode):

```bash
python3 -c "import sys;sys.path.insert(0,'lib');from compression import hsq_decompress;\
open('/tmp/dn386.bin','wb').write(hsq_decompress(open('gamedata/DN386.HSQ','rb').read()))"
objdump -D -b binary -m i386 -M i8086,addr16,data16 \
  --start-address=0xSTART --stop-address=0xSTOP /tmp/dn386.bin
```

All addresses below are **file offsets into the decompressed `DN386.bin`**.

## ABI — the far jump table (`E9 rel16` ×20 @ 0x0000)

| # | Target | Role |
|---|--------|------|
| 0 | 0x0867 | mode-13h init (`int 10h`, AL=0x13) |
| 1 | 0x08D9 | get framebuffer params (AX=0xA000, CX=0xFA00=64000) |
| 2 | 0x08E2 | string find/install (utility, not graphics) |
| 3 | 0x16FC | save/restore box, 4-bit expand |
| 4 | 0x17B4 | restore page from 0xFA00 back-buffer (stride 0x140) |
| **5** | **0x0E2D** | **sprite blit — main entry** |
| **6** | **0x1315** | **clipped sprite draw** |
| 7 | 0x1ABD | 1-bpp mono/mask blit (cursor / shadow / glyphs) |
| 8 | 0x185F | block copy with clip rect |
| 9–10 | 0x17E1/0x17E3 | filled-rect / horizontal-line (`rep stos`) |
| 11,13,15 | 0x19E4 | clear page (0x3E80 dwords = 64000 B) |
| 12,14,16 | 0x19F5 | scaled blits (4 sub-pixel phases) |
| 17 | 0x1A91 | stretch blit (stride 0x280 = 2× vertical) |
| 18 | 0x1AAE | copy 0x2F80 dwords |
| 19 | 0x186F | fill variant |

`0x0AF8` is the shared **coordinate → framebuffer-offset** helper used by almost
every primitive: clamps Y ≤ 199, computes `DI = y*320 + x + base` (`y*320` via
the `y·256 + y·64` shift trick); `base` at `cs:0x1A3` is set by `0x0AEE`
(`mov dx,0x140; mul dx`).

## Sprite blit (entry 0x0E2D) — validated against our codec

The blitter was checked line-by-line against `tools/sprite_decoder.py` /
`web/src/codecs/sprite.ts` and matches exactly:

- Sprite flags in the first word (`DI`): `0x6000`=h-flip, `0x4000`=v-flip,
  `0x2000`=decode-mode; `and ax,0x1FF` = 9-bit width.
- Row blitters `0x0B2D` (forward) / `0x0BB8` (mirrored, `std`) / `0x144B`
  (clipped): `lods al; or al,al; js` selects a **transparent-skip run** vs a
  **literal run** (header byte-1 bit 7 = compression flag); **two 4-bit pixels
  per byte** (`and dl,al` low nibble, `shr ah,4` high nibble); palette index
  **0 = transparent** (skip without writing); `add dh,al` applies the sprite's
  palette offset; end-of-row `add di,0x140` (320 stride).
- `0x1315` is the clipping front-end: clip bounds from `[bp+0..6]` (x0,x1,y0,y1),
  trims source/width/height, then enters the same blitter family.

**Conclusion:** the project's sprite codec is faithful to the engine. The
overlays contain **no per-sprite frame-cel sequence tables and no animation
timer** (no `int 1Ah`, no BDA-tick read) — the cel order + timing are owned by
the CS1 game-logic caller, which hands the blitter an explicit source pointer
each tick. `detectAnimations` (grouping same-size frames) therefore remains the
correct heuristic until CS1 is recovered.

## Globe / planet sphere-fill (0x1B8C)

Reached via a runtime-patched far-call pointer (the project's
`gfx_vtable_func_29`), not the static ABI table.

- **Geometry:** disc centred at **screen column 160, rows 79–80** (cursor seeds
  `0x6360` = 79·320+160 and `0x64A0` = 80·320+160), filled **symmetrically
  outward** (`std;stosb` left + `cld;stosb` right about col 160). Source pitch is
  **200 bytes per scanline** (`add 0xC8` per step) = the GLOBDATA latitude-block
  size; per-row half-width follows TABLAT (199·cos lat); radius constants
  `mov cx,0x58` (=88). Top hemisphere fills upward (row stride −320), bottom
  downward (+320), flipped at the equator marker.
- **Palette (verified @0x1D1E):**

  ```
  AL = src & 0x0F ;  AH = src & 0x30
  if (AH == 0x10 && AL < 8) AL += 0x0C
  AL += 0x10
  ```

  The planet disc is drawn in the fixed low palette **bank 0x10–0x1F** (a few
  shades reach 0x23 via the special case) — **not** the 0x80–0xBF colour-cycle
  band, and **not** a 256-level ramp. The actual RGB of indices 0x10–0x23 is
  uploaded to the DAC at runtime and is not in the overlay. Implemented as
  `planetPaletteIndex` / `planetColor` in `web/src/codecs/map.ts`.
- **Rotation:** there is **no per-frame longitude accumulator** in this
  primitive; rotation is produced by the CS1 caller re-projecting the source
  workspace each frame, so the longitude *origin* lives upstream (not recovered).

## Palette colour-cycling (0x0AC4) — verified in both overlays

`mov si,0x73F` (palette work buffer) → `rep movsw` (0x5E words) rotates the band
one slot with wrap, then `mov bx,0x80; mov cx,0x40` (start 0x80, count 64) →
DAC writer at `0x0A50` (`mov dx,0x3C8` @0x0A6C, 6-bit RGB triplets, optional
grayscale-blend path gated on `cs:0x1BD`). This is the single hardcoded cycle
band: **DAC indices 0x80–0xBF (64 colours)**, one slot/frame. Exposed as
`ENGINE_CYCLE_RANGE` in `web/src/codecs/palette.ts`. (The globe does **not** use
this band; it animates some other element, e.g. the star/space backdrop.)

## Screen-effect animations (not sprite cels)

Two genuine internal phase counters exist (in both overlays), driving full-screen
effects rather than character animation:

- **Wipe/transition @0x2C42** (counter `cs:0x24FA`): `incw` per call, count ×6
  scanlines/frame, paired with the **double-buffer page-flip @0x2447**
  (`xchg cs:0x24F4, cs:0x24F6`).
- **Looping scroll @0x3408** (counter `cs:0x3501`): increments and wraps at a
  caller-supplied limit; runs a short RET-terminated row micro-program — a cyclic
  background-scroll effect.

Both take their parameters from the caller; neither is a frame-sequence table.
