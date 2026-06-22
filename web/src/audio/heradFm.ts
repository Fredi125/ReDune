/**
 * ReDune — OPL2-style 2-operator FM voice for WebAudio, driven by the real
 * HERAD instrument patches (modulator + carrier: MULT, TL, ADSR, waveform,
 * feedback/connection). This is a faithful-in-structure approximation of the
 * YM3812 (2-op FM, 4 OPL2 waveforms), NOT a cycle-exact emulator — but the
 * timbres come from the actual decoded instrument data.
 */
import { OPL_MULT, type HeradInstrument } from "../codecs/herad";

/** The 4 OPL2 operator waveforms as functions of phase p in [0,1). */
const WAVEFNS: ((p: number) => number)[] = [
  (p) => Math.sin(2 * Math.PI * p),
  (p) => {
    const s = Math.sin(2 * Math.PI * p);
    return s > 0 ? s : 0;
  },
  (p) => Math.abs(Math.sin(2 * Math.PI * p)),
  (p) => {
    const m = (2 * Math.PI * p) % Math.PI;
    return m < Math.PI / 2 ? Math.sin(m) : 0;
  },
];

/** Build the 4 OPL2 waveforms as PeriodicWaves (via a small DFT). */
export function oplWaves(ctx: BaseAudioContext): PeriodicWave[] {
  const N = 2048;
  const K = 64;
  return WAVEFNS.map((fn) => {
    const real = new Float32Array(K + 1);
    const imag = new Float32Array(K + 1);
    for (let k = 1; k <= K; k++) {
      let a = 0;
      let b = 0;
      for (let n = 0; n < N; n++) {
        const s = fn(n / N);
        const ang = (2 * Math.PI * k * n) / N;
        a += s * Math.cos(ang);
        b += s * Math.sin(ang);
      }
      real[k] = (2 * a) / N;
      imag[k] = (2 * b) / N;
    }
    return ctx.createPeriodicWave(real, imag, { disableNormalization: false });
  });
}

/** OPL envelope rate (0..15) → seconds (higher rate = faster). */
function rt(rate: number): number {
  const r = Math.max(0, Math.min(15, rate));
  return Math.min(2.5, Math.max(0.001, 0.0012 * Math.pow(2, (15 - r) / 1.7)));
}

export function midiToFreq(note: number): number {
  return 440 * Math.pow(2, (note - 69) / 12);
}

/**
 * Schedule one FM note. Returns the time (s) at which it finishes.
 */
export function playFmNote(
  ctx: AudioContext,
  dest: AudioNode,
  waves: PeriodicWave[],
  inst: HeradInstrument,
  freq: number,
  vel: number,
  t0: number,
  t1: number,
): number {
  // The carrier sounds at the note's written pitch; the modulator keeps the
  // patch's modulator:carrier MULT ratio (so the FM timbre is unchanged) instead
  // of multiplying the carrier's pitch by carMul. Dune's patches use carMul≠1 on
  // most voices, and a literal carrier·carMul scrambles the octaves (see opl2.ts
  // noteToFreqReg). carMul of 0 → OPL 0.5×.
  const carMulV = OPL_MULT[inst.carMul] ?? 1;
  const modMulV = OPL_MULT[inst.modMul] ?? 1;
  const carFreq = freq;
  const modFreq = freq * (modMulV / (carMulV || 1));
  const carBase = 1 - inst.carOut / 63;
  const velScale = inst.carOutVel !== 0 ? 0.3 + 0.7 * (vel / 127) : 1;
  const peak = Math.max(0.0001, Math.min(1, carBase) * velScale * 0.26);

  const aT = rt(inst.carA);
  const dT = rt(inst.carD);
  const sLvl = 1 - inst.carS / 15;
  const rT = rt(inst.carR);
  const rel = Math.max(t1, t0 + aT + dT);

  const carrier = ctx.createOscillator();
  carrier.setPeriodicWave(waves[inst.carWave] ?? waves[0]);
  carrier.frequency.value = carFreq;
  const carGain = ctx.createGain();
  const g = carGain.gain;
  g.setValueAtTime(0.0001, t0);
  g.exponentialRampToValueAtTime(peak, t0 + aT);
  g.exponentialRampToValueAtTime(Math.max(0.0001, peak * sLvl), t0 + aT + dT);
  g.setValueAtTime(Math.max(0.0001, peak * sLvl), rel);
  g.exponentialRampToValueAtTime(0.0001, rel + rT);
  carrier.connect(carGain);
  carGain.connect(dest);

  const mod = ctx.createOscillator();
  mod.setPeriodicWave(waves[inst.modWave] ?? waves[0]);
  mod.frequency.value = modFreq;
  const modGain = ctx.createGain();
  const modBase = 1 - inst.modOut / 63;
  const mA = rt(inst.modA);
  const mD = rt(inst.modD);
  const mSus = 1 - inst.modS / 15;

  if (inst.con > 0) {
    // FM: modulator drives the carrier's frequency
    const depth = carFreq * 7 * Math.max(0, modBase);
    const mg = modGain.gain;
    mg.setValueAtTime(0, t0);
    mg.linearRampToValueAtTime(depth, t0 + mA);
    mg.linearRampToValueAtTime(depth * mSus, t0 + mA + mD);
    mg.setValueAtTime(depth * mSus, rel);
    mg.linearRampToValueAtTime(0, rel + rT);
    mod.connect(modGain);
    modGain.connect(carrier.frequency);
  } else {
    // additive: both operators sound
    const mp = Math.max(0.0001, Math.min(1, modBase) * velScale * 0.18);
    const mg = modGain.gain;
    mg.setValueAtTime(0.0001, t0);
    mg.exponentialRampToValueAtTime(mp, t0 + mA);
    mg.exponentialRampToValueAtTime(Math.max(0.0001, mp * mSus), t0 + mA + mD);
    mg.setValueAtTime(Math.max(0.0001, mp * mSus), rel);
    mg.exponentialRampToValueAtTime(0.0001, rel + rT);
    mod.connect(modGain);
    modGain.connect(dest);
  }

  const end = rel + rT + 0.03;
  carrier.start(t0);
  carrier.stop(end);
  mod.start(t0);
  mod.stop(end);
  return end;
}
