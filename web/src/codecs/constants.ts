/**
 * ReDune codecs — game constants.
 * Ported from lib/constants.py (subset needed by the web app).
 * All offsets are 0-indexed (CD v3.7).
 */

export const SAVE_OFFSETS = {
  dialogue_state: 0x3338,
  rallied_troops: 0x4446,
  charisma: 0x4447,
  game_stage: 0x4448,
  spice: 0x44be,
  sietch_block: 0x451e,
  troop_block: 0x4cc8,
  npc_data: 0x53f4,
  smuggler_data: 0x54f6,
  datetime: 0x5592,
  contact_distance: 0x5594,
} as const;

export const SIETCH_COUNT = 70;
export const SIETCH_SIZE = 28;
export const TROOP_COUNT = 68;
export const TROOP_SIZE = 27;

export const GAME_STAGES: Record<number, string> = {
  0x00: "Start (intro sequence)",
  0x01: "Met Gurney",
  0x04: "Find Prospectors",
  0x08: "Prospectors Found",
  0x0c: "Found Communications",
  0x10: "Found Harvester",
  0x14: "Post-Harvester",
  0x18: "Ecology Intro",
  0x1c: "Water Discovery",
  0x20: "Mid-Game",
  0x24: "Sietch Tuek",
  0x28: "Pre-Stilgar",
  0x2c: "Take Stilgar",
  0x30: "Post-Stilgar",
  0x35: "Leto Left",
  0x38: "Harkonnen Push",
  0x3c: "Resistance",
  0x40: "Counter-Attack",
  0x48: "Pre-Worm Riding",
  0x4f: "Can Worm-Ride",
  0x50: "Rode Worm",
  0x58: "Army Building",
  0x60: "Find Chani",
  0x64: "Chani Kidnapped",
  0x68: "Chani Returned",
  0xc8: "Ending / Victory",
};

export const TROOP_JOBS: Record<number, string> = {
  0: "None/Idle",
  1: "Spice Mining",
  2: "Spice Mining (alt)",
  3: "Military Training",
  4: "Military (Army)",
  5: "Ecology (Vegetation)",
  6: "Equipment Manufacturing",
  7: "Spice Prospecting",
  8: "Espionage",
};

export const EQUIPMENT_FLAGS: [number, string][] = [
  [0x01, "Knives"],
  [0x02, "Krysknives"],
  [0x04, "LaserGuns"],
  [0x08, "Weirding"],
  [0x10, "Atomics"],
  [0x20, "Bulbs"],
  [0x40, "Harvesters"],
  [0x80, "Ornis"],
];

export function equipmentStr(val: number): string {
  const parts = EQUIPMENT_FLAGS.filter(([bit]) => val & bit).map(([, n]) => n);
  return parts.length ? parts.join(", ") : "None";
}

export const LOCATION_FIRST_NAMES: Record<number, string> = {
  1: "Arrakeen", 2: "Carthag", 3: "Tuono", 4: "Habbanya",
  5: "Oxtyn", 6: "Tsympo", 7: "Bledan", 8: "Ergsun",
  9: "Haga", 10: "Cielago", 11: "Sihaya", 12: "Celimyn",
};

export const LOCATION_SECOND_NAMES: Record<number, string> = {
  1: "(Atreides)", 2: "(Harkonnen)", 3: "Tabr", 4: "Timin",
  5: "Tuek", 6: "Harg", 7: "Clam", 8: "Tsymyn",
  9: "Siet", 10: "Pyons", 11: "Pyort",
};

export function locationName(region: number, subregion: number): string {
  const first = LOCATION_FIRST_NAMES[region] ?? `?${region}`;
  const second = LOCATION_SECOND_NAMES[subregion] ?? `?${subregion}`;
  return subregion <= 2 ? `${first} ${second}` : `${first}-${second}`;
}

export const SIETCH_STATUS_FLAGS: [number, string][] = [
  [0x01, "Vegetation"],
  [0x02, "InBattle"],
  [0x10, "Inventory"],
  [0x20, "WindTrap"],
  [0x40, "Prospected"],
  [0x80, "Undiscovered"],
];

export function sietchStatusStr(val: number): string {
  const parts = SIETCH_STATUS_FLAGS.filter(([bit]) => val & bit).map(([, n]) => n);
  return parts.length ? parts.join(", ") : "Visible";
}

// Which decoration sprite sheet pairs with each SAL room file (normal mode).
// From calc_SAL_index in DNCDPRG.ASM (lib/constants.py SAL_SPRITE_NORMAL).
export const SAL_DECORATION: Record<string, string> = {
  "SIET.SAL": "MAP2.HSQ",
  "PALACE.SAL": "MIRROR.HSQ",
  "VILG.SAL": "DS0.HSQ",
  "HARK.SAL": "DS1.HSQ",
};

export function recommendedDecoration(salName: string): string | undefined {
  return SAL_DECORATION[salName.toUpperCase()];
}

// CONDIT VM operations: index -> [name, symbol, description]
export const CONDIT_OPS: Record<number, [string, string, string]> = {
  0x00: ["EQ", "==", "dx == ax"],
  0x01: ["LT", "<u", "dx < ax unsigned"],
  0x02: ["GT", ">u", "dx > ax unsigned"],
  0x03: ["NE", "!=", "dx != ax"],
  0x04: ["LE", "<=s", "dx <= ax signed"],
  0x05: ["GE", ">=s", "dx >= ax signed"],
  0x06: ["ADD", "+", "dx = dx + ax"],
  0x07: ["SUB", "-", "dx = dx - ax"],
  0x08: ["AND", "&", "dx = dx & ax"],
  0x09: ["OR", "|", "dx = dx | ax"],
};

// Known DS-segment variables referenced by CONDIT bytecodes (offset -> name)
export const CONDIT_VARIABLES: Record<number, string> = {
  0x0002: "GameElapsedTime",
  0x000a: "MapFlags",
  0x000b: "SietchTroopCount",
  0x0010: "SietchBitfield1",
  0x0012: "SietchBitfield2",
  0x0023: "DialogueChoiceState",
  0x0025: "SpiceShipmentCarry",
  0x0026: "SpiceShipmentFlag",
  0x002a: "GameStage",
  0x002b: "GameStageChanged",
  0x0090: "NPCEncounterCounter",
  0x00bf: "BattleFlags",
  0x00c2: "BattlePhase",
  0x00c8: "HarkonnenStrength",
  0x00ea: "EventNPCId",
  0x00f4: "DayNightPhase",
  0x00fb: "WormSignFlag",
  0x00fc: "ConditVarFC",
};
