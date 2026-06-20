/**
 * ReDune codecs — HERAD music decoder + Standard MIDI File exporter.
 * Port of tools/herad_decoder.py (parse_herad / parse_track_events / export_midi).
 *
 * Three variants: OPL2/AdLib (.HSQ), AGD (Tandy/PCjr), M32 (Roland MT-32).
 * The original is FM/MT-32 synthesis; this exports a playable General MIDI .mid
 * (byte-identical to the Python --midi output). In-browser FM playback would
 * need an OPL2 emulator and is out of scope.
 */
import { isHsq, hsqDecompress } from "./compression";

export const FMT_OPL2 = "OPL2";
export const FMT_AGD = "AGD";
export const FMT_M32 = "M32";
export type HeradFmt = typeof FMT_OPL2 | typeof FMT_AGD | typeof FMT_M32;

const DATA_START_OPL2 = 0x0032;
const DATA_START_AGD = 0x0052;
const META_OFFSET = 0x2c;
export const HERAD_INST_SIZE = 40;

/** F-number per chromatic note (C..B), from adplug CheradPlayer::FNum. */
export const HERAD_FNUM = [343, 364, 385, 408, 433, 459, 486, 515, 546, 579, 614, 650];
/** OPL2 frequency-multiplier ratios indexed by the 4-bit MULT field. */
export const OPL_MULT = [0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 12, 12, 15, 15];

function u16(d: Uint8Array, o: number): number {
  return d[o] | (d[o + 1] << 8);
}
function extOf(name: string): string {
  const m = /\.([^.]+)$/.exec(name);
  return m ? "." + m[1].toUpperCase() : "";
}

export function detectFormat(data: Uint8Array, name = ""): HeradFmt {
  const ext = extOf(name);
  if (ext === ".M32") return FMT_M32;
  if (ext === ".AGD") return FMT_AGD;
  if (data.length >= 4 && u16(data, 2) === DATA_START_AGD) return FMT_AGD;
  return FMT_OPL2;
}

function getDataStart(fmt: HeradFmt, data: Uint8Array): number {
  if (fmt === FMT_AGD) return u16(data, 2);
  return DATA_START_OPL2;
}

export interface HeradTrack {
  index: number;
  offset: number;
  size: number;
  data: Uint8Array;
}
export interface HeradInfo {
  format: HeradFmt;
  fileSize: number;
  instOffset: number;
  trackOffsets: number[];
  tracks: HeradTrack[];
  nInstruments: number;
}

export function parseHerad(data: Uint8Array, name = ""): HeradInfo {
  const fmt = detectFormat(data, name);
  const dataStart = getDataStart(fmt, data);
  if (data.length < dataStart) throw new Error(`HERAD file too small (${data.length} bytes)`);

  const instOffset = u16(data, 0);
  const maxTracks = fmt === FMT_AGD ? 20 : 11;
  const trackOffsets: number[] = [];
  for (let i = 1; i < maxTracks; i++) {
    if (i * 2 + 1 >= Math.min(data.length, META_OFFSET)) break;
    const off = u16(data, i * 2);
    if (off === 0) break;
    trackOffsets.push(off);
  }
  const nInstruments = data.length >= META_OFFSET + 2 ? u16(data, META_OFFSET) : 0;

  const tracks: HeradTrack[] = [];
  for (let ti = 0; ti < trackOffsets.length; ti++) {
    const start = trackOffsets[ti];
    const end = ti + 1 < trackOffsets.length ? trackOffsets[ti + 1] : instOffset;
    if (start < data.length && end <= data.length && end > start) {
      tracks.push({ index: ti, offset: start, size: end - start, data: data.subarray(start, end) });
    }
  }
  return { format: fmt, fileSize: data.length, instOffset, trackOffsets, tracks, nInstruments };
}

function readVlq(data: Uint8Array, pos: number): [number, number] {
  let value = 0;
  while (pos < data.length) {
    const b = data[pos++];
    value = (value << 7) | (b & 0x7f);
    if (!(b & 0x80)) break;
  }
  return [value, pos];
}

type Event = { delta: number; type: string; data: number[] };

export function parseTrackEvents(track: Uint8Array, fmt: HeradFmt): Event[] {
  const events: Event[] = [];
  let pos = 0;
  // OPL2/AGD uses the RESTRICTED status set Cryo's HERAD revision actually emits:
  // {0x80,0x90,0xC0,0xD0,0xFF}, where 0xD0 carries TWO data bytes. Verified
  // against adplug's CheradPlayer (herad.cpp) and found to DIVERGE: adplug's
  // current model (dispatch on status&0xF0; 0xD0=1-byte aftertouch; 0xE0=1-byte
  // pitch-bend; unknown status ends the track) recovers only ~1.5k of the ~24k
  // notes in Dune's decompressed tracks and kills ~20 tracks outright, for both
  // v1 and v2 note-off lengths. The set below yields perfectly balanced
  // NOTE_ON/NOTE_OFF (see the HERAD note-balance test), so Dune predates that
  // adplug revision — do NOT "modernise" this to the adplug dispatch.
  const isStatus = fmt === FMT_M32 ? (b: number) => b >= 0x80 : (b: number) => b === 0x80 || b === 0x90 || b === 0xc0 || b === 0xd0 || b === 0xff;

  while (pos < track.length) {
    const b = track[pos];
    let delta = 0;
    let status: number;
    if (isStatus(b)) {
      status = b;
    } else {
      [delta, pos] = readVlq(track, pos);
      if (pos >= track.length) break;
      status = track[pos];
    }

    if (fmt === FMT_M32) {
      const type = status & 0xf0;
      const ch = status & 0x0f;
      if (type === 0x90) {
        if (pos + 2 >= track.length) break;
        events.push({ delta, type: "NOTE_ON", data: [track[pos + 1], track[pos + 2], ch] });
        pos += 3;
      } else if (type === 0x80) {
        if (pos + 2 >= track.length) break;
        events.push({ delta, type: "NOTE_OFF", data: [track[pos + 1], track[pos + 2], ch] });
        pos += 3;
      } else if (type === 0xc0) {
        if (pos + 1 >= track.length) break;
        events.push({ delta, type: "PROG_CHG", data: [track[pos + 1], ch] });
        pos += 2;
      } else if (type === 0xb0) {
        if (pos + 2 >= track.length) break;
        events.push({ delta, type: "CONTROL", data: [track[pos + 1], track[pos + 2], ch] });
        pos += 3;
      } else if (type === 0xe0) {
        if (pos + 2 >= track.length) break;
        events.push({ delta, type: "PITCH_BEND", data: [track[pos + 1], track[pos + 2], ch] });
        pos += 3;
      } else if (type === 0xd0) {
        if (pos + 1 >= track.length) break;
        events.push({ delta, type: "AFTERTOUCH", data: [track[pos + 1], ch] });
        pos += 2;
      } else if (status === 0xff) {
        events.push({ delta, type: "VOICE", data: [status] });
        pos += 1;
      } else if (type === 0xf0) {
        pos += 1;
        while (pos < track.length && track[pos] !== 0xf7) pos += 1;
        if (pos < track.length) pos += 1;
      } else {
        events.push({ delta, type: "UNKNOWN", data: [status] });
        pos += 1;
      }
    } else {
      if (status === 0x90) {
        if (pos + 2 >= track.length) break;
        events.push({ delta, type: "NOTE_ON", data: [track[pos + 1], track[pos + 2]] });
        pos += 3;
      } else if (status === 0x80) {
        if (pos + 2 >= track.length) break;
        events.push({ delta, type: "NOTE_OFF", data: [track[pos + 1], track[pos + 2]] });
        pos += 3;
      } else if (status === 0xc0) {
        if (pos + 1 >= track.length) break;
        events.push({ delta, type: "PROG_CHG", data: [track[pos + 1]] });
        pos += 2;
      } else if (status === 0xd0) {
        if (pos + 2 >= track.length) break;
        events.push({ delta, type: "CONTROL", data: [track[pos + 1], track[pos + 2]] });
        pos += 3;
      } else {
        events.push({ delta, type: "VOICE", data: [status] });
        pos += 1;
      }
    }
  }
  return events;
}

function midiVlq(value: number): number[] {
  if (value < 0) value = 0;
  const buf = [value & 0x7f];
  value >>= 7;
  while (value > 0) {
    buf.push(0x80 | (value & 0x7f));
    value >>= 7;
  }
  return buf.reverse();
}

const clamp7 = (v: number) => Math.min(v, 127);

/** Convert a (decompressed) HERAD buffer to a Standard MIDI File (format 1). */
export function exportMidi(data: Uint8Array, name = "", ticksPerQuarter = 120): Uint8Array {
  const info = parseHerad(data, name);
  const fmt = info.format;
  const out: number[] = [];
  const pushStr = (s: string) => {
    for (let i = 0; i < s.length; i++) out.push(s.charCodeAt(i));
  };
  const pushBE32 = (v: number) => out.push((v >>> 24) & 0xff, (v >>> 16) & 0xff, (v >>> 8) & 0xff, v & 0xff);
  const pushBE16 = (v: number) => out.push((v >> 8) & 0xff, v & 0xff);

  // MThd
  pushStr("MThd");
  pushBE32(6);
  pushBE16(1); // format 1
  pushBE16(info.tracks.length);
  pushBE16(ticksPerQuarter);

  for (let ti = 0; ti < info.tracks.length; ti++) {
    const events = parseTrackEvents(info.tracks[ti].data, fmt);
    const ev: number[] = [];
    for (const e of events) {
      const vlq = midiVlq(e.delta);
      if (fmt === FMT_M32) {
        const ch = e.data.length >= 2 ? e.data[e.data.length - 1] : ti;
        if (e.type === "NOTE_ON") {
          const vel = e.data[1] > 0 ? clamp7(e.data[1]) : 64;
          ev.push(...vlq, 0x90 | ch, clamp7(e.data[0]), vel);
        } else if (e.type === "NOTE_OFF") {
          ev.push(...vlq, 0x80 | ch, clamp7(e.data[0]), 64);
        } else if (e.type === "PROG_CHG") {
          ev.push(...vlq, 0xc0 | ch, clamp7(e.data[0]));
        } else if (e.type === "CONTROL") {
          ev.push(...vlq, 0xb0 | ch, clamp7(e.data[0]), clamp7(e.data[1]));
        } else if (e.type === "PITCH_BEND") {
          ev.push(...vlq, 0xe0 | ch, e.data[0] & 0x7f, e.data[1] & 0x7f);
        }
      } else {
        const ch = ti < 16 ? ti : 15;
        if (e.type === "NOTE_ON") {
          const vel = e.data[1] > 0 ? clamp7(e.data[1]) : 64;
          ev.push(...vlq, 0x90 | ch, clamp7(e.data[0]), vel);
        } else if (e.type === "NOTE_OFF") {
          ev.push(...vlq, 0x80 | ch, clamp7(e.data[0]), 64);
        } else if (e.type === "PROG_CHG") {
          ev.push(...vlq, 0xc0 | ch, clamp7(e.data[0]));
        } else if (e.type === "CONTROL") {
          ev.push(...vlq, 0xb0 | ch, clamp7(e.data[0]), clamp7(e.data[1]));
        } else if (e.type === "VOICE") {
          if (e.delta > 0) ev.push(...vlq, 0xb0 | ch, 0x7b, 0);
        }
      }
    }
    ev.push(0x00, 0xff, 0x2f, 0x00); // end of track
    pushStr("MTrk");
    pushBE32(ev.length);
    for (const x of ev) out.push(x);
  }
  return Uint8Array.from(out);
}

export interface HeradLoad {
  info: HeradInfo;
  midi: Uint8Array;
  instruments: HeradInstrument[];
}

/**
 * A decoded HERAD FM instrument patch (40-byte record). Field layout from
 * adplug's herad_inst_data struct; the OPL operator params drive FM synthesis.
 */
export interface HeradInstrument {
  index: number;
  mode: number;
  feedback: number;
  con: number; // >0 = FM (modulator->carrier), <=0 = additive
  modMul: number;
  carMul: number;
  modOut: number; // total level (attenuation 0..63, 0 = loudest)
  carOut: number;
  modA: number;
  modD: number;
  modS: number;
  modR: number;
  carA: number;
  carD: number;
  carS: number;
  carR: number;
  modWave: number;
  carWave: number;
  modOutVel: number;
  carOutVel: number;
}

const i8 = (b: number) => (b > 127 ? b - 256 : b);

/** Parse the OPL2 instrument block (40-byte records starting at instOffset). */
export function parseInstruments(data: Uint8Array, instOffset: number): HeradInstrument[] {
  const out: HeradInstrument[] = [];
  if (instOffset <= 0 || instOffset >= data.length) return out;
  const n = Math.floor((data.length - instOffset) / HERAD_INST_SIZE);
  for (let i = 0; i < n; i++) {
    const o = instOffset + i * HERAD_INST_SIZE;
    if (o + HERAD_INST_SIZE > data.length) break;
    out.push({
      index: i,
      mode: i8(data[o]),
      modMul: data[o + 3] & 15,
      feedback: data[o + 4] & 7,
      modA: data[o + 5] & 15,
      modS: data[o + 6] & 15,
      modD: data[o + 8] & 15,
      modR: data[o + 9] & 15,
      modOut: data[o + 10] & 63,
      con: i8(data[o + 14]),
      carMul: data[o + 16] & 15,
      carA: data[o + 18] & 15,
      carS: data[o + 19] & 15,
      carD: data[o + 21] & 15,
      carR: data[o + 22] & 15,
      carOut: data[o + 23] & 63,
      modWave: data[o + 28] & 3,
      carWave: data[o + 29] & 3,
      modOutVel: i8(data[o + 30]),
      carOutVel: i8(data[o + 31]),
    });
  }
  return out;
}

/** Load a HERAD file (decompressing HSQ if needed) and produce its MIDI + instruments. */
export function loadHerad(raw: Uint8Array, name = ""): HeradLoad {
  const data = isHsq(raw) ? hsqDecompress(raw) : raw;
  const info = parseHerad(data, name);
  return { info, midi: exportMidi(data, name), instruments: parseInstruments(data, info.instOffset) };
}
