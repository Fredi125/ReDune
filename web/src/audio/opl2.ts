/**
 * ReDune — faithful YM3812 (OPL2) software synthesiser.
 *
 * Unlike `heradFm.ts` (a WebAudio oscillator-node approximation), this is a
 * sample-accurate OPL2 model you program through real register writes, exactly
 * as Dune's `DNADL` driver does (ground truth: `docs/adlib_driver.md`):
 *   - 9 channels × 2 operators, modulator/carrier slot tables @0x71/0x7A
 *   - operator output via the real log-sin + exp attenuation pipeline (so the
 *     characteristic OPL quantisation/harmonics are reproduced, not idealised
 *     sine×gain)
 *   - the 4 OPL2 waveforms (reg 0xE0), selectable per operator
 *   - phase-domain FM with modulator self-**feedback** (reg 0xC0) — the single
 *     biggest timbre the oscillator approximation was missing
 *   - FM vs additive connection (reg 0xC0 bit 0)
 *   - per-operator ADSR envelope generator (regs 0x60/0x80) with KSR + the
 *     OPL attack curve, and EG-type (sustaining vs percussive, reg 0x20 bit 5)
 *   - note→frequency through the engine's own F-number table (reg 0xA0/0xB0)
 *
 * Known simplifications vs cycle-exact hardware (documented honestly — the
 * cycle-exact YM3812 core is a separate low-priority item): KSL (key-scale
 * level) is not applied; vibrato/tremolo (AM/VIB depth, reg 0xBD) is ignored;
 * the EG rate→time mapping is calibrated (doubling per +4 rate, anchored to the
 * AdLib timings) rather than bit-exact; the FM modulation index is a fixed
 * depth. Every output sample still comes from the real OPL operator algorithm.
 */
import { type HeradInstrument, type HeradFmt, parseTrackEvents } from "../codecs/herad";

export const OPL_RATE = 3579545 / 72; // 49715.9 Hz — the chip's native sample rate

// OPL frequency-multiplier table (reg 0x20 low nibble).
const MULT = [0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 12, 12, 15, 15];

// Channel → operator register offsets (docs/adlib_driver.md @0x71 / @0x7A).
const SLOT_MOD = [0x00, 0x01, 0x02, 0x08, 0x09, 0x0a, 0x10, 0x11, 0x12];
const SLOT_CAR = [0x03, 0x04, 0x05, 0x0b, 0x0c, 0x0d, 0x13, 0x14, 0x15];

// Reverse map: operator register offset → { channel, carrier }.
const OP_OF_OFFSET = new Map<number, { ch: number; car: boolean }>();
for (let c = 0; c < 9; c++) {
  OP_OF_OFFSET.set(SLOT_MOD[c], { ch: c, car: false });
  OP_OF_OFFSET.set(SLOT_CAR[c], { ch: c, car: true });
}

// --- attenuation tables (1/256-of-log2 units; amplitude = 2^(-att/256)) ----
const LOGSIN = new Float64Array(256); // quarter-wave |sin| attenuation
const AMP_FRAC = new Float64Array(256); // 2^(-f/256), f in 0..255  → [1, 0.5)
const POW2_NEG = new Float64Array(64); // 2^(-w)
for (let i = 0; i < 256; i++) {
  LOGSIN[i] = Math.round(-Math.log2(Math.sin(((i + 0.5) / 256) * (Math.PI / 2))) * 256);
  AMP_FRAC[i] = Math.pow(2, -i / 256);
}
for (let w = 0; w < 64; w++) POW2_NEG[w] = Math.pow(2, -w);

/** Attenuation (≥0, integer-ish) → linear amplitude in [0,1], OPL-quantised. */
function attToAmp(att: number): number {
  if (att >= 0x1fff) return 0;
  const a = att | 0;
  return AMP_FRAC[a & 0xff] * POW2_NEG[(a >> 8) & 63];
}

/**
 * One OPL2 operator's attenuation for a phase position, applying the selected
 * waveform. Returns the log-sin attenuation plus a sign and a mute flag.
 */
function waveAtten(phase01: number, waveform: number): { att: number; neg: boolean; mute: boolean } {
  let p = phase01 - Math.floor(phase01); // [0,1)
  if (p < 0) p += 1;
  const idx10 = Math.floor(p * 1024) & 0x3ff;
  const quad = idx10 >> 8; // 0..3
  const within = idx10 & 0xff;
  switch (waveform) {
    case 1: // half-sine: positive humps, silence on the negative half
      if (quad >= 2) return { att: 0, neg: false, mute: true };
      return { att: LOGSIN[quad & 1 ? 255 - within : within], neg: false, mute: false };
    case 2: // |sine|
      return { att: LOGSIN[quad & 1 ? 255 - within : within], neg: false, mute: false };
    case 3: // quarter pulse-sine: rising quarters only
      if (quad & 1) return { att: 0, neg: false, mute: true };
      return { att: LOGSIN[within], neg: false, mute: false };
    default: // 0: full sine
      return { att: LOGSIN[quad & 1 ? 255 - within : within], neg: quad >= 2, mute: false };
  }
}

type EgState = "off" | "attack" | "decay" | "sustain" | "release";

interface Operator {
  // patch params
  mult: number;
  tl: number; // total level 0..63
  ar: number;
  dr: number;
  sl: number;
  rr: number;
  ksr: boolean;
  egType: boolean; // true = sustaining
  waveform: number;
  // runtime
  phase: number; // cycles, [0,1)
  freq: number; // Hz at current note (incl. mult)
  eg: number; // attenuation level 0 (loud) .. 511 (silent)
  state: EgState;
  attMul: number; // per-sample multiplier during attack
  decInc: number; // per-sample +att during decay
  relInc: number; // per-sample +att during release
  out: number; // last output (for feedback / FM)
  prev: number; // output before last (feedback averaging)
}

function newOp(): Operator {
  return {
    mult: 1, tl: 0, ar: 0, dr: 0, sl: 0, rr: 0, ksr: false, egType: false, waveform: 0,
    phase: 0, freq: 0, eg: 511, state: "off", attMul: 0, decInc: 0, relInc: 0, out: 0, prev: 0,
  };
}

interface Channel {
  fnum: number;
  block: number;
  keyOn: boolean;
  fb: number; // feedback 0..7
  con: boolean; // true = additive, false = FM
  ops: [Operator, Operator]; // [modulator, carrier]
}

export class OPL2 {
  private readonly sr: number;
  private readonly chans: Channel[] = [];
  /** EG full-sweep (511 units) reference time at effective-rate 48, in seconds. */
  private static readonly T_REF = 0.006;
  /** Live tuning knobs (1 = faithful default). Set before/after construction. */
  fmDepth = 1;
  envScale = 1;
  feedbackScale = 1;

  constructor(sampleRate: number) {
    this.sr = sampleRate;
    for (let c = 0; c < 9; c++) {
      this.chans.push({ fnum: 0, block: 0, keyOn: false, fb: 0, con: false, ops: [newOp(), newOp()] });
    }
  }

  /** Effective EG rate 0..63 from a 4-bit param + key-scale. */
  private effRate(param: number, ch: Channel, op: Operator): number {
    if (param <= 0) return 0;
    const ksn = (ch.block << 1) | (ch.fnum >> 9);
    const rof = op.ksr ? ksn : ksn >> 2;
    return Math.min(63, param * 4 + rof);
  }

  /** Decay/release: linear-in-dB increment (level units / sample). */
  private linInc(rate: number): number {
    if (rate <= 0) return 0;
    return (511 / (this.sr * OPL2.T_REF * this.envScale)) * Math.pow(2, (rate - 48) / 4);
  }

  /** Recompute an operator's per-sample envelope coefficients for its channel. */
  private recalcEg(ch: Channel, op: Operator): void {
    const ar = this.effRate(op.ar, ch, op);
    const dr = this.effRate(op.dr, ch, op);
    const rr = this.effRate(op.rr, ch, op);
    // Attack approaches 0 attenuation exponentially over ~T_REF·2^(-(ar-48)/4).
    if (ar <= 0) {
      op.attMul = 1; // never attacks
    } else {
      const tA = OPL2.T_REF * this.envScale * Math.pow(2, -(ar - 48) / 4);
      op.attMul = Math.exp(Math.log(0.5 / 511) / Math.max(1, tA * this.sr));
    }
    op.decInc = this.linInc(dr);
    op.relInc = this.linInc(rr);
  }

  /** Sustain level (att units) from the 4-bit SL field. */
  private static slLevel(sl: number): number {
    return sl >= 15 ? 496 : sl * 16; // 3 dB/step ≈ 16 units; 15 → 93 dB
  }

  write(reg: number, val: number): void {
    val &= 0xff;
    const hi = reg & 0xf0;
    const lo = reg & 0x0f;
    if (reg >= 0x20 && reg <= 0x35 && OP_OF_OFFSET.has(reg - 0x20)) {
      const { ch, car } = OP_OF_OFFSET.get(reg - 0x20)!;
      const op = this.chans[ch].ops[car ? 1 : 0];
      op.mult = MULT[val & 0x0f];
      op.ksr = (val & 0x10) !== 0;
      op.egType = (val & 0x20) !== 0;
      op.freq = this.baseFreq(this.chans[ch]) * op.mult;
    } else if (reg >= 0x40 && reg <= 0x55 && OP_OF_OFFSET.has(reg - 0x40)) {
      const { ch, car } = OP_OF_OFFSET.get(reg - 0x40)!;
      this.chans[ch].ops[car ? 1 : 0].tl = val & 0x3f; // KSL (top 2 bits) not applied
    } else if (reg >= 0x60 && reg <= 0x75 && OP_OF_OFFSET.has(reg - 0x60)) {
      const { ch, car } = OP_OF_OFFSET.get(reg - 0x60)!;
      const op = this.chans[ch].ops[car ? 1 : 0];
      op.ar = (val >> 4) & 0x0f;
      op.dr = val & 0x0f;
      this.recalcEg(this.chans[ch], op);
    } else if (reg >= 0x80 && reg <= 0x95 && OP_OF_OFFSET.has(reg - 0x80)) {
      const { ch, car } = OP_OF_OFFSET.get(reg - 0x80)!;
      const op = this.chans[ch].ops[car ? 1 : 0];
      op.sl = (val >> 4) & 0x0f;
      op.rr = val & 0x0f;
      this.recalcEg(this.chans[ch], op);
    } else if (reg >= 0xe0 && reg <= 0xf5 && OP_OF_OFFSET.has(reg - 0xe0)) {
      const { ch, car } = OP_OF_OFFSET.get(reg - 0xe0)!;
      this.chans[ch].ops[car ? 1 : 0].waveform = val & 0x03;
    } else if (hi === 0xa0 && lo < 9) {
      const ch = this.chans[lo];
      ch.fnum = (ch.fnum & 0x300) | val;
      this.refreshFreq(ch);
    } else if (hi === 0xb0 && lo < 9) {
      const ch = this.chans[lo];
      ch.fnum = (ch.fnum & 0xff) | ((val & 0x03) << 8);
      ch.block = (val >> 2) & 0x07;
      this.refreshFreq(ch);
      this.setKeyOn(ch, (val & 0x20) !== 0);
    } else if (hi === 0xc0 && lo < 9) {
      const ch = this.chans[lo];
      ch.fb = (val >> 1) & 0x07;
      ch.con = (val & 0x01) !== 0;
    }
    // 0x01 (WSE), 0x08 (NTS), 0xBD (rhythm/AM-VIB) accepted but not modelled.
  }

  private baseFreq(ch: Channel): number {
    return ch.fnum * (1 << ch.block) * (OPL_RATE / (1 << 20));
  }

  private refreshFreq(ch: Channel): void {
    const base = this.baseFreq(ch);
    ch.ops[0].freq = base * ch.ops[0].mult;
    ch.ops[1].freq = base * ch.ops[1].mult;
  }

  private setKeyOn(ch: Channel, on: boolean): void {
    if (on && !ch.keyOn) {
      for (const op of ch.ops) {
        this.recalcEg(ch, op);
        op.state = "attack";
        op.phase = 0;
      }
    } else if (!on && ch.keyOn) {
      for (const op of ch.ops) op.state = "release";
    }
    ch.keyOn = on;
  }

  /** Advance an operator's envelope one sample. */
  private stepEg(op: Operator): void {
    switch (op.state) {
      case "attack":
        op.eg *= op.attMul;
        if (op.eg <= 0.5) { op.eg = 0; op.state = "decay"; }
        break;
      case "decay": {
        op.eg += op.decInc;
        const sl = OPL2.slLevel(op.sl);
        if (op.eg >= sl) { op.eg = sl; op.state = op.egType ? "sustain" : "release"; }
        break;
      }
      case "sustain":
        break; // hold until key-off
      case "release":
        op.eg += op.relInc;
        if (op.eg >= 511) { op.eg = 511; op.state = "off"; }
        break;
      default:
        break;
    }
  }

  /** Evaluate one operator: advance phase + envelope, return signed output [-1,1]. */
  private runOp(op: Operator, phaseMod: number): number {
    op.phase += op.freq / this.sr;
    if (op.phase >= 1 || op.phase <= -1) op.phase -= Math.floor(op.phase);
    this.stepEg(op);
    if (op.state === "off") { op.prev = op.out; op.out = 0; return 0; }
    const { att, neg, mute } = waveAtten(op.phase + phaseMod, op.waveform);
    let v = 0;
    if (!mute) {
      const total = att + (op.eg * 8 + op.tl * 32); // eg: 0.1875 dB/unit, tl: 0.75 dB/unit
      v = attToAmp(total) * (neg ? -1 : 1);
    }
    op.prev = op.out;
    op.out = v;
    return v;
  }

  /** Generate one mono sample (sum of all channels), nominal range ~[-1,1]. */
  generate(): number {
    let acc = 0;
    for (const ch of this.chans) {
      const [mod, car] = ch.ops;
      if (mod.state === "off" && car.state === "off") continue;
      // modulator self-feedback: phase mod from its own recent output
      const fb = ch.fb > 0 ? ((mod.out + mod.prev) * 0.5) * Math.pow(2, ch.fb - 7) * this.feedbackScale : 0;
      const mOut = this.runOp(mod, fb);
      if (ch.con) {
        // additive: both operators sound directly
        acc += (this.runOp(car, 0) + mOut) * 0.5;
      } else {
        // FM: modulator output deviates the carrier phase
        acc += this.runOp(car, mOut * this.fmDepth);
      }
    }
    return acc;
  }
}

// --- high-level helpers: program a channel from a HERAD patch + play notes ---

/** Envelope-type override: keep the patch's bit, or force all voices one way. */
export type EgMode = "faithful" | "sustain" | "pluck";

/** Write a 2-op HERAD instrument patch into OPL channel `ch`. */
export function programChannel(opl: OPL2, ch: number, inst: HeradInstrument, egMode: EgMode = "faithful"): void {
  const m = SLOT_MOD[ch];
  const c = SLOT_CAR[ch];
  const egOf = (v: boolean) => (egMode === "sustain" ? true : egMode === "pluck" ? false : v);
  // Real 0x20 byte: EG-type (bit5) + KSR (bit4) + MULT (bits3-0), decoded from
  // the patch (see herad.ts). Most Dune voices are PERCUSSIVE (EG-type 0) — they
  // must decay past the sustain level, not hold — so forcing sustaining (the old
  // shortcut) made plucks/hits drone. AM/VIB (bits 7/6) need the global 0xBD LFO
  // we don't model, so they stay 0.
  opl.write(0x20 + m, ((egOf(inst.modEgType) ? 0x20 : 0) | (inst.modKsr ? 0x10 : 0) | (inst.modMul & 0x0f)) & 0xff);
  opl.write(0x20 + c, ((egOf(inst.carEgType) ? 0x20 : 0) | (inst.carKsr ? 0x10 : 0) | (inst.carMul & 0x0f)) & 0xff);
  opl.write(0x40 + m, inst.modOut & 0x3f);
  opl.write(0x40 + c, inst.carOut & 0x3f);
  opl.write(0x60 + m, ((inst.modA & 0x0f) << 4) | (inst.modD & 0x0f));
  opl.write(0x60 + c, ((inst.carA & 0x0f) << 4) | (inst.carD & 0x0f));
  opl.write(0x80 + m, ((inst.modS & 0x0f) << 4) | (inst.modR & 0x0f));
  opl.write(0x80 + c, ((inst.carS & 0x0f) << 4) | (inst.carR & 0x0f));
  opl.write(0xe0 + m, inst.modWave & 0x03);
  opl.write(0xe0 + c, inst.carWave & 0x03);
  // OPL connection bit: 0 = FM (modulator→carrier), 1 = additive. HERAD `con`
  // is >0 for FM, so invert.
  opl.write(0xc0 + ch, ((inst.feedback & 0x07) << 1) | (inst.con > 0 ? 0 : 1));
}

/** Note → target sounding frequency (Hz); A4 (note 69) = 440 (MIDI/heradFm convention). */
export function noteHz(note: number): number {
  return 440 * Math.pow(2, (note - 69) / 12);
}

/** Any frequency (Hz) → OPL (fnum, block); fnum kept within the chip's 10-bit range. */
export function freqToReg(freq: number): { fnum: number; block: number } {
  if (freq <= 0) return { fnum: 0, block: 0 };
  let block = 0;
  let fnum = (freq * (1 << 20)) / OPL_RATE; // F-number at block 0
  while (fnum > 1023 && block < 7) {
    fnum /= 2;
    block++;
  }
  return { fnum: Math.max(0, Math.min(1023, Math.round(fnum))), block };
}

/**
 * Convert a HERAD note to (fnum, block) for a channel whose **carrier** MULT is
 * `carMul` (the OPL multiplier value 0.5/1/2/3/5…). The chip multiplies each
 * operator's phase rate by its MULT, so to make the carrier (the audible voice
 * in FM, and the loud operator in additive) sound at the note's *written* pitch
 * we program the channel base at `noteHz/carMul`. The modulator (base·modMul)
 * then sounds at `noteHz·modMul/carMul`, i.e. the modulator:carrier ratio — the
 * FM timbre — is preserved exactly; only the octave is anchored to the score.
 *
 * Why not literal `block = note/12` + the F-number table (what the hardware
 * does)? Dune's patches set carrier MULT≠1 on most voices, so a literal render
 * scrambles the arrangement — SIETCHM's lead lands at A6–A7 and its bass at
 * E4–E5, shrill and out of register. The shipped driver keeps every voice at
 * its written octave via per-channel setup done at runtime (the slot/transpose
 * tables it reads @0x135 are zero-filled in the static driver blob, i.e. filled
 * by the engine), so the in-tune, musically-coherent result is the carrier at
 * the written pitch with the ratio preserved.
 */
export function noteToFreqReg(note: number, carMul = 1): { fnum: number; block: number } {
  return freqToReg(noteHz(note) / (carMul || 1));
}

export function noteOn(opl: OPL2, ch: number, note: number, carMul = 1): void {
  const { fnum, block } = noteToFreqReg(note, carMul);
  opl.write(0xa0 + ch, fnum & 0xff);
  opl.write(0xb0 + ch, 0x20 | (block << 2) | ((fnum >> 8) & 0x03));
}

export function noteOff(opl: OPL2, ch: number, note: number, carMul = 1): void {
  const { fnum, block } = noteToFreqReg(note, carMul);
  opl.write(0xb0 + ch, (block << 2) | ((fnum >> 8) & 0x03)); // key-on bit cleared
}

interface NoteInst {
  start: number; // seconds
  end: number;
  note: number;
  instIdx: number;
}

/** Live song-level tuning knobs surfaced in the Music tab. */
export interface SynthParams {
  transpose: number; // semitones added to every note
  fmDepth: number; // FM modulation index scale (brightness)
  envScale: number; // envelope time scale (>1 = longer notes)
  feedbackScale: number; // modulator self-feedback scale
  gain: number; // master output gain
  carrierLiteral: boolean; // false = carrier at written pitch (musical); true = apply carrier MULT (hardware)
  egMode: EgMode; // faithful | force sustain | force pluck
}

export const DEFAULT_SYNTH_PARAMS: SynthParams = {
  transpose: 0, fmDepth: 1, envScale: 1, feedbackScale: 1, gain: 1, carrierLiteral: false, egMode: "faithful",
};

/**
 * Offline-render a HERAD song to a mono Float32Array at `sampleRate`, driving
 * the OPL2 with real register writes. Voices are allocated across the chip's 9
 * channels (oldest stolen when oversubscribed), matching hardware. `params` are
 * the Music-tab tuning knobs (tempo is separate, via `bpm`). `startSec` seeks in
 * and `maxSeconds` bounds the window length, so a live re-tune can re-render a
 * few seconds around the playhead instead of the whole (2–4 s to render) song.
 */
export function renderHeradOpl2(
  tracks: { data: Uint8Array }[],
  fmt: HeradFmt,
  insts: HeradInstrument[],
  bpm: number,
  sampleRate: number,
  ticksPerQuarter: number,
  maxSeconds = 240,
  params: SynthParams = DEFAULT_SYNTH_PARAMS,
  startSec = 0,
): Float32Array {
  const tick = 60 / bpm / ticksPerQuarter;
  const notes: NoteInst[] = [];
  for (const trk of tracks) {
    const events = parseTrackEvents(trk.data, fmt);
    let cur = 0;
    let prog = 0;
    const active = new Map<number, { instIdx: number; start: number }>();
    for (const e of events) {
      cur += e.delta * tick;
      if (e.type === "PROG_CHG") prog = e.data[0];
      else if (e.type === "NOTE_ON" && e.data[1] > 0) active.set(e.data[0], { instIdx: prog, start: cur });
      else if (e.type === "NOTE_OFF" || (e.type === "NOTE_ON" && e.data[1] === 0)) {
        const a = active.get(e.data[0]);
        if (a) { notes.push({ start: a.start, end: cur, note: e.data[0], instIdx: a.instIdx }); active.delete(e.data[0]); }
      }
    }
    for (const [note, a] of active) notes.push({ start: a.start, end: cur + 0.3, note, instIdx: a.instIdx });
  }
  if (notes.length === 0) return new Float32Array(0);

  // Render the window [t0, winEnd). With startSec=0 this is the whole song (the
  // default); a positive startSec seeks in (notes already sounding are re-keyed
  // at the window start), and maxSeconds bounds the window length — so live
  // tuning can re-render just a few seconds around the playhead instead of the
  // whole 2–4 s song.
  let songEnd = 0;
  for (const n of notes) songEnd = Math.max(songEnd, n.end);
  const t0 = Math.max(0, startSec);
  const winEnd = Math.min(songEnd + 0.6, t0 + maxSeconds);
  if (winEnd <= t0) return new Float32Array(0);
  const total = Math.ceil((winEnd - t0) * sampleRate);
  const out = new Float32Array(total);

  const ons = [...notes].map((n, i) => ({ ...n, id: i })).sort((a, b) => a.start - b.start);
  const offs = [...ons].sort((a, b) => a.end - b.end);
  const chOfNote = new Int32Array(notes.length).fill(-1);
  const chFreeAt = new Float64Array(9).fill(-Infinity); // when each channel last went idle
  const chNote = new Int32Array(9).fill(-1);

  const opl = new OPL2(sampleRate);
  opl.fmDepth = params.fmDepth;
  opl.envScale = params.envScale;
  opl.feedbackScale = params.feedbackScale;
  const carMulOf = (inst?: HeradInstrument) => (params.carrierLiteral ? 1 : inst ? MULT[inst.carMul] : 1);
  const DEFAULT = insts[0];
  const alloc = (): number => {
    for (let c = 0; c < 9; c++) if (chNote[c] < 0) return c;
    let ch = 0;
    for (let c = 1; c < 9; c++) if (chFreeAt[c] < chFreeAt[ch]) ch = c;
    return ch; // steal the channel idle longest / oldest
  };
  const keyOn = (n: NoteInst & { id: number }): void => {
    const inst = insts[n.instIdx] ?? DEFAULT;
    if (!inst) return;
    const ch = alloc();
    programChannel(opl, ch, inst, params.egMode);
    noteOn(opl, ch, n.note + params.transpose, carMulOf(inst));
    chOfNote[n.id] = ch;
    chNote[ch] = n.note;
    chFreeAt[ch] = Infinity;
  };

  let oi = 0; // next on
  let fi = 0; // next off
  if (t0 > 0) {
    // seek: sound the notes already playing at the window start, then skip past
    // every event before it.
    for (const n of ons) if (n.start < t0 && n.end > t0) keyOn(n);
    while (oi < ons.length && ons[oi].start < t0) oi++;
    while (fi < offs.length && offs[fi].end <= t0) fi++;
  }

  let peak = 1e-6;
  for (let s = 0; s < total; s++) {
    const t = t0 + s / sampleRate;
    // key-offs first so a freed channel can be reused this sample
    while (fi < offs.length && offs[fi].end <= t) {
      const n = offs[fi++];
      const ch = chOfNote[n.id];
      if (ch >= 0 && chNote[ch] === n.note) {
        noteOff(opl, ch, n.note + params.transpose, carMulOf(insts[n.instIdx] ?? DEFAULT));
        chFreeAt[ch] = t;
        chNote[ch] = -1;
      }
    }
    while (oi < ons.length && ons[oi].start <= t) keyOn(ons[oi++]);
    const v = opl.generate();
    out[s] = v;
    const a = v < 0 ? -v : v;
    if (a > peak) peak = a;
  }
  // normalise to avoid clipping while keeping headroom, then apply master gain
  const g = (0.85 / peak) * params.gain;
  for (let s = 0; s < total; s++) out[s] *= g;
  return out;
}
