# Dune 1992 — Sound Drivers (`DN*.HSQ`) and the OPL2 Register Map

The `DN*.HSQ` files are HSQ-compressed real-mode (8086) **sound drivers**, one
per output device. They are the *authoritative* description of how Dune programs
each chip — this is the code that actually shipped, so it beats any third-party
player as a reference (recall that adplug's HERAD event model does **not** match
Dune's files — see `herad.ts`). Decode/annotate any of them with:

```bash
python tools/driver_decoder.py gamedata/DNADL.HSQ        # annotated landmarks
python tools/driver_decoder.py gamedata/DNADL.HSQ --asm  # + full disassembly
```

| Driver | Device | Audio ports |
|--------|--------|-------------|
| `DNADL` | AdLib / OPL2 (YM3812) | 0x388/0x389 |
| `DNADG` / `DNADP` | AdLib Gold / variants | 0x388/0x389 |
| `DNSDB` / `DNSBP` | Sound Blaster (+ OPL) | base detected at runtime; programs the PIC (0x20/0x21, 0xA0/0xA1) for its IRQ |
| `DNMID` | Roland MT-32 / MPU-401 | MPU-401 base configured at runtime |
| `DNPCS` / `DNPCS2` | PC speaker | 0x61 (speaker gate) + PIT |
| `DN386` | 386 main / dispatcher | — |
| `DNVGA` | VGA setup | — |

All drivers share a common ABI: the file begins with a **7-entry jump table**
(`E9 rel16` ×7 = init / play / stop / … ), so the engine calls a driver the same
way regardless of device.

## OPL2 register-write protocol (`DNADL`, ground truth)

The register writer lives at **0x0A35**. Convention: **AL = register**, **AH =
value** (callers load `AX = (value<<8)|reg`).

```
0A35  mov dx,0x388     ; OPL address port
0A38  out dx,al        ; select register (AL)
0A39  in al,dx  ×7     ; ~3.3 µs post-select delay (read status port)
0A40  inc dx           ; -> 0x389 data port
0A41  mov al,ah
0A43  out dx,al        ; write value (AH)
0A44  in al,dx  ×~35   ; ~23 µs post-write delay
```

**Init** (entry 0, @0x01D6) is textbook OPL2 bring-up:

| reg | value | meaning |
|-----|-------|---------|
| 0x01 | 0x20 | enable **waveform-select** (WSE) |
| 0xBD | 0x00 | rhythm mode off, AM/VIB depth off |
| 0x08 | 0x40 | NTS (note-select) |

## Channel → operator slot offsets (@0x0071 / @0x007A)

The two operators of channel *c* live at `base + slot[c]`:

```
modulator slots @0x71:  00 01 02 08 09 0A 10 11 12
carrier   slots @0x7A:  03 04 05 0B 0C 0D 13 14 15
```

## Instrument load (@0x0958, ground truth)

Loading a 2-op patch writes exactly the six standard OPL2 register groups
(operator regs use `base + slot`, channel reg uses `base + channel`):

| reg base | per | OPL2 meaning |
|----------|-----|--------------|
| 0x20 | operator | AM / VIB / EG-type / KSR / **multiplier** |
| 0x40 | operator | KSL / **total level** (attenuation) |
| 0x60 | operator | **attack** / **decay** rate |
| 0x80 | operator | **sustain** level / **release** rate |
| 0xE0 | operator | **waveform** select (0–3 on OPL2) |
| 0xC0 | channel  | **feedback** / connection (FM vs AM) |

This is the target layout for the HERAD 40-byte instrument patch decoded by
`parseInstruments` (`herad_decoder.py` / `web/src/codecs/herad.ts`): its
`mod*/car*` fields are the per-operator 0x20/0x40/0x60/0x80/0xE0 bytes, and
`feedback`/`connection` are the 0xC0 byte.

## Note → frequency (@0x0047)

Note-on uses one octave of **F-numbers** plus a block (octave), written by the
frequency routine at **0x0A27** to `0xA0+ch` (F-number low) and `0xB0+ch`
(F-number high | block<<2 | key-on 0x20):

```
fnum[note % 12] @0x47:
  0x157 0x16C 0x181 0x198 0x1B1 0x1CB 0x1E6 0x203 0x222 0x243 0x266 0x28A
block = note // 12
```

Converted to Hz (`fnum · 3579545/72 / 2^(20−block)`) this table is **equal
temperament** within OPL F-number quantization (≤ ~8 cents), which confirms that
the Hz-based 2-op FM synth in `web/src/audio/heradFm.ts` uses the correct tuning
— HERAD note numbers are plain semitones, no exotic scale.

## The OPL2 software synth (`web/src/audio/opl2.ts`)

This register map is implemented faithfully by `class OPL2`: a sample-accurate
YM3812 model you drive through the exact register writes above. `programChannel`
loads a HERAD 2-op patch (the 0x20/0x40/0x60/0x80/0xE0/0xC0 groups), `noteOn`
writes 0xA0/0xB0 using the @0x47 F-number table, and `renderHeradOpl2` plays a
whole song by allocating notes across the 9 channels and offline-rendering to a
buffer. It reproduces modulator self-**feedback**, the 4 OPL2 waveforms via the
real log-sin/exp attenuation pipeline (so the chip's quantisation/harmonics are
present, not idealised sine×gain), and FM-vs-additive routing — the things the
older WebAudio oscillator synth (`heradFm.ts`) could not. Honest remaining
approximations: KSL, vibrato/tremolo (reg 0xBD), a fixed FM depth, and a
calibrated (not register-cycle-exact) EG rate→time mapping.

### Carrier MULT and pitch (`noteToFreqReg`)

The instrument-load routine (@0x0958, decoded above) confirms each operator's
4-bit **MULT** is written to its `0x20` register: modulator `MULT = patch[+1]`,
carrier `MULT = patch[+0xE]` (driver `si` = our 40-byte record base **+2**, so
these are our `modMul` @`+3` / `carMul` @`+16` — verified field-for-field,
including the `0x40/0x60/0x80/0xE0` groups and both waveforms). On the chip each
operator's phase rate is `fnum·MULT`, so a literal render puts the **carrier**
(the audible voice) at `note·carMul`.

Dune's patches, however, set `carMul ≠ 1` on most voices (e.g. SIETCHM inst 0 =
**5**, inst 2 = 4; ARRAKIS lead inst 10 = 3). Rendering that literally scrambles
the arrangement — SIETCHM's bass (notes C2–C3, inst 0) lands at E4–E5 and its
lead (inst 2) at A6–A7, shrill and out of register; ARRAKIS's melody jumps ~1.5
octaves when it switches inst 9 (carMul 1) → inst 10 (carMul 3). The shipped
driver keeps voices at their **written** octave via per-channel setup done at
runtime — the slot/transpose word table it indexes at `cs:[bx+0x135]` is
**zero-filled** in the static driver blob (i.e. populated by the engine, not a
code constant), so it can't be read statically. So `noteToFreqReg` programs the
channel base at `noteHz / carMul`: the carrier then sounds at the score pitch and
the modulator at `noteHz·modMul/carMul`, i.e. the modulator:carrier **ratio**
(the FM timbre) is preserved exactly while the octave is anchored to the music.
A regression test asserts a `carMul=4` voice still sounds note 69 at ~440 Hz.

> **Companion finding (graphics):** the *palette* hardware code is **not** in
> `DNCDPRG.EXE` (it has no `3C8h`/`3C9h` I/O) — it lives in the `DNVGA`/`DN386`
> overlays, where the one hardcoded colour-cycle band is **DAC 0x80–0xBF** (64
> entries, one slot/frame; rotate routine @DNVGA 0x0ADC / DN386 0x0AC4). See
> `web/src/codecs/palette.ts` (`ENGINE_CYCLE_RANGE`).

## What the static analysis cannot resolve

Sound Blaster / MT-32 *audio* base ports are configured at runtime (from
autodetect or the install config), so they don't appear as immediates in the
disassembly. `DNSDB`'s visible ports are the **PIC** writes (0x20/0x21, 0xA0/0xA1)
where it installs/acknowledges its DMA IRQ. The exact SB/MT-32 byte streams would
need dynamic tracing; the OPL2 map above, by contrast, is fully static and
complete.
