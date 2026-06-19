/**
 * ReDune codecs — save file reader/writer.
 * Direct port of tools/save_editor.py (DuneSave class).
 * Handles F7 RLE transparently; edits operate on the decompressed buffer.
 */

import { f7Compress, f7Decompress } from "./compression";
import {
  SAVE_OFFSETS as OFF,
  SIETCH_COUNT,
  SIETCH_SIZE,
  TROOP_COUNT,
  TROOP_SIZE,
  NPC_COUNT,
  NPC_STRIDE,
  SMUGGLER_COUNT,
  SMUGGLER_STRIDE,
  NPC_SPRITES,
  GAME_STAGES,
  TROOP_JOBS,
  equipmentStr,
  locationName,
  sietchStatusStr,
} from "./constants";

export interface NPC {
  index: number;
  spriteId: number;
  spriteName: string;
  roomLocation: number;
  typeOfPlace: number;
  dialogueAvailable: number;
  exactPlace: number;
  forDialogue: number;
}

export interface Smuggler {
  index: number;
  region: number;
  haggle: number;
  harvesters: number;
  ornithopters: number;
  krysknives: number;
  laserguns: number;
  weirding: number;
  priceHarvesters: number;
  priceOrnithopters: number;
  priceKrysknives: number;
  priceLaserguns: number;
  priceWeirding: number;
}

export interface Troop {
  index: number;
  troop_id: number;
  next_troop: number;
  prev_troop: number;
  job: number;
  job_name: string;
  sietch_id: number;
  spice_skill: number;
  army_skill: number;
  eco_skill: number;
  equipment: number;
  equipment_str: string;
  population: number;
  motivation: number;
  spice_mining_rate: number;
  dissatisfaction: number;
}

export interface Sietch {
  index: number;
  byte0: number;
  region: number;
  subregion: number;
  name: string;
  coord1: number;
  coord2: number;
  pos_x: number;
  pos_y: number;
  appearance: number;
  troop_id: number;
  status: number;
  status_str: string;
  discovered: boolean;
  prospected: boolean;
  windtrap: boolean;
  inventory: boolean;
  in_battle: boolean;
  vegetation: boolean;
  stage_gate: number;
  spice_field: number;
  spice_amount: number;
  spice_density: number;
  harvesters: number;
  ornithopters: number;
  knives: number;
  guns: number;
  weirding: number;
  atomics: number;
  bulbs: number;
}

// field name -> [offset within record, size]
const TROOP_FIELDS: Record<string, [number, number]> = {
  troop_id: [0, 1], job: [3, 1], sietch_id: [5, 1],
  spice_skill: [8, 1], army_skill: [9, 1], eco_skill: [10, 1],
  equipment: [11, 1], equip: [11, 1],
  population: [12, 2], motivation: [14, 1],
  spice_mining_rate: [15, 1], dissatisfaction: [25, 1],
};

const SIETCH_FIELDS: Record<string, [number, number]> = {
  byte0: [0x00, 1], region: [0x01, 1], subregion: [0x02, 1],
  appearance: [0x09, 1], troop_id: [0x0a, 1], troop: [0x0a, 1],
  status: [0x0b, 1], stage_gate: [0x0c, 1],
  spice_field: [0x11, 1], spice_amount: [0x12, 1], spice: [0x12, 1],
  spice_density: [0x13, 1],
  harvesters: [0x15, 1], ornithopters: [0x16, 1],
  knives: [0x17, 1], guns: [0x18, 1],
  weirding: [0x19, 1], atomics: [0x1a, 1], bulbs: [0x1b, 1],
};

export class DuneSave {
  data: Uint8Array;
  compressedSize: number;
  decompressedSize: number;

  constructor(raw: Uint8Array) {
    this.data = f7Decompress(raw);
    this.compressedSize = raw.length;
    this.decompressedSize = this.data.length;
    // Highest field we read is contact_distance @0x5594. A real save
    // decompresses to ~22146 bytes; anything much shorter is corrupt.
    const MIN = OFF.contact_distance + 1;
    if (this.data.length < MIN) {
      throw new Error(
        `This .SAV decompressed to only ${this.data.length} bytes (a valid save is ~22146). ` +
          `The file looks corrupted — on Windows this is almost always Git rewriting line endings in binary ` +
          `files. Fix: 'git config core.autocrlf false', then re-checkout (see the repo .gitattributes / README).`,
      );
    }
  }

  u8(o: number): number {
    return this.data[o];
  }
  u16(o: number): number {
    return this.data[o] | (this.data[o + 1] << 8);
  }
  w8(o: number, v: number): void {
    this.data[o] = v & 0xff;
  }
  w16(o: number, v: number): void {
    this.data[o] = v & 0xff;
    this.data[o + 1] = (v >> 8) & 0xff;
  }

  // --- globals ---
  get gameStage() { return this.u8(OFF.game_stage); }
  set gameStage(v: number) { this.w8(OFF.game_stage, v); }
  get charisma() { return this.u8(OFF.charisma); }
  set charisma(v: number) { this.w8(OFF.charisma, v); }
  get ralliedTroops() { return this.u8(OFF.rallied_troops); }
  set ralliedTroops(v: number) { this.w8(OFF.rallied_troops, v); }
  get spice() { return this.u16(OFF.spice); }
  set spice(v: number) { this.w16(OFF.spice, v); }
  get datetimeRaw() { return this.u16(OFF.datetime); }
  get hour() { return this.datetimeRaw & 0xf; }
  get day() { return this.datetimeRaw >> 4; }
  setTime(day?: number, hour?: number) {
    const d = day ?? this.day;
    const h = hour ?? this.hour;
    this.w16(OFF.datetime, (d << 4) | (h & 0xf));
  }
  get contactDistance() { return this.u8(OFF.contact_distance); }
  set contactDistance(v: number) { this.w8(OFF.contact_distance, v); }

  get stageName(): string {
    return GAME_STAGES[this.gameStage] ?? "Unknown";
  }

  // --- troops ---
  troopOffset(idx: number) { return OFF.troop_block + idx * TROOP_SIZE; }

  troop(idx: number): Troop {
    const off = this.troopOffset(idx);
    const d = this.data;
    const job = d[off + 3];
    const equipment = d[off + 11];
    return {
      index: idx,
      troop_id: d[off + 0], next_troop: d[off + 1], prev_troop: d[off + 2],
      job, job_name: TROOP_JOBS[job] ?? `?${job}`,
      sietch_id: d[off + 5],
      spice_skill: d[off + 8], army_skill: d[off + 9], eco_skill: d[off + 10],
      equipment, equipment_str: equipmentStr(equipment),
      population: d[off + 12] | (d[off + 13] << 8),
      motivation: d[off + 14], spice_mining_rate: d[off + 15],
      dissatisfaction: d[off + 25],
    };
  }

  allTroops(): Troop[] {
    return Array.from({ length: TROOP_COUNT }, (_, i) => this.troop(i));
  }

  setTroopField(idx: number, field: string, value: number): boolean {
    const f = TROOP_FIELDS[field];
    if (!f) return false;
    const [foff, fsize] = f;
    const off = this.troopOffset(idx) + foff;
    if (fsize === 1) this.w8(off, value);
    else this.w16(off, value);
    return true;
  }

  // --- sietches ---
  sietchOffset(idx: number) { return OFF.sietch_block + idx * SIETCH_SIZE; }

  sietch(idx: number): Sietch {
    const off = this.sietchOffset(idx);
    const d = this.data;
    const status = d[off + 0x0b];
    return {
      index: idx,
      byte0: d[off + 0x00],
      region: d[off + 0x01],
      subregion: d[off + 0x02],
      name: locationName(d[off + 0x01], d[off + 0x02]),
      coord1: d[off + 0x03],
      coord2: d[off + 0x04],
      pos_x: d[off + 0x07],
      pos_y: d[off + 0x08],
      appearance: d[off + 0x09],
      troop_id: d[off + 0x0a],
      status,
      status_str: sietchStatusStr(status),
      discovered: !(status & 0x80),
      prospected: !!(status & 0x40),
      windtrap: !!(status & 0x20),
      inventory: !!(status & 0x10),
      in_battle: !!(status & 0x02),
      vegetation: !!(status & 0x01),
      stage_gate: d[off + 0x0c],
      spice_field: d[off + 0x11],
      spice_amount: d[off + 0x12],
      spice_density: d[off + 0x13],
      harvesters: d[off + 0x15],
      ornithopters: d[off + 0x16],
      knives: d[off + 0x17],
      guns: d[off + 0x18],
      weirding: d[off + 0x19],
      atomics: d[off + 0x1a],
      bulbs: d[off + 0x1b],
    };
  }

  allSietches(): Sietch[] {
    return Array.from({ length: SIETCH_COUNT }, (_, i) => this.sietch(i));
  }

  setSietchField(idx: number, field: string, value: number): boolean {
    const f = SIETCH_FIELDS[field];
    if (!f) return false;
    this.w8(this.sietchOffset(idx) + f[0], value);
    return true;
  }

  // --- NPCs (0x53F4, 16 × 16 bytes) ---
  npcOffset(idx: number) { return OFF.npc_data + idx * NPC_STRIDE; }

  npc(idx: number): NPC {
    const o = this.npcOffset(idx);
    const d = this.data;
    return {
      index: idx,
      spriteId: d[o],
      spriteName: NPC_SPRITES[d[o]] ?? `0x${d[o].toString(16).toUpperCase().padStart(2, "0")}`,
      roomLocation: d[o + 2],
      typeOfPlace: d[o + 3],
      dialogueAvailable: d[o + 4],
      exactPlace: d[o + 5],
      forDialogue: d[o + 6],
    };
  }
  allNpcs(): NPC[] {
    return Array.from({ length: NPC_COUNT }, (_, i) => this.npc(i));
  }
  /** field offsets within an NPC record: spriteId 0, roomLocation 2, typeOfPlace 3, dialogueAvailable 4, exactPlace 5, forDialogue 6 */
  setNpcByte(idx: number, fieldOffset: number, value: number) {
    this.w8(this.npcOffset(idx) + fieldOffset, value);
  }

  // --- Smugglers (0x54F6, 6 × 17 bytes) ---
  smugglerOffset(idx: number) { return OFF.smuggler_data + idx * SMUGGLER_STRIDE; }

  smuggler(idx: number): Smuggler {
    const o = this.smugglerOffset(idx);
    const d = this.data;
    return {
      index: idx,
      region: d[o],
      haggle: d[o + 1],
      harvesters: d[o + 4],
      ornithopters: d[o + 5],
      krysknives: d[o + 6],
      laserguns: d[o + 7],
      weirding: d[o + 8],
      priceHarvesters: d[o + 9],
      priceOrnithopters: d[o + 10],
      priceKrysknives: d[o + 11],
      priceLaserguns: d[o + 12],
      priceWeirding: d[o + 13],
    };
  }
  allSmugglers(): Smuggler[] {
    return Array.from({ length: SMUGGLER_COUNT }, (_, i) => this.smuggler(i));
  }
  setSmugglerByte(idx: number, fieldOffset: number, value: number) {
    this.w8(this.smugglerOffset(idx) + fieldOffset, value);
  }

  /** Re-compress the (possibly edited) buffer back to a .SAV byte array. */
  serialize(): Uint8Array {
    return f7Compress(this.data);
  }
}

export const SAVE_FIELD_NAMES = {
  troop: Object.keys(TROOP_FIELDS),
  sietch: Object.keys(SIETCH_FIELDS),
};
