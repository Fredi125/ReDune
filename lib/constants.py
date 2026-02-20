"""
dune1992-re: Game constants and data tables.

All offsets are 0-indexed. DuneEdit2 uses 1-indexed offsets (subtract 1).
Decoded from: DNCDPRG.EXE disassembly, Cryogenic/Spice86 C# source, DuneEdit2.
"""

# =============================================================================
# SAVE FILE LAYOUT (CD v3.7)
# =============================================================================

SAVE_OFFSETS = {
    "screen_data":      0x0000,   # ~17KB F7 RLE compressed screen capture
    "dialogue_state":   0x3338,   # Runtime copy of DIALOGUE.HSQ state
    "time_counters":    0x441E,   # Time-related counters
    "rallied_troops":   0x4446,   # uint8: number of rallied troops
    "charisma":         0x4447,   # uint8: raw charisma (GUI = byte / 2)
    "game_stage":       0x4448,   # uint8: ★ master story progression ★
    "spice":            0x44BE,   # uint16 LE: spice stockpile (×10 = displayed kg)
    "sietch_block":     0x451E,   # 70 × 28 bytes: sietch/location records
    "troop_sentinel":   0x4CC6,   # FF FF sentinel before troop block
    "troop_block":      0x4CC8,   # 68 × 27 bytes: troop records
    "npc_data":         0x53F4,   # NPC data block (16 bytes per record?)
    "smuggler_data":    0x54F6,   # Smuggler data
    "datetime":         0x5592,   # uint16 LE: bits[3:0]=hour, bits[15:4]=day
    "contact_distance": 0x5594,   # uint8: ornithopter contact distance
}

SIETCH_COUNT = 70
SIETCH_SIZE  = 28
TROOP_COUNT  = 68
TROOP_SIZE   = 27


# =============================================================================
# GAME STAGE VALUES
# =============================================================================

GAME_STAGES = {
    0x00: "Start (intro sequence)",
    0x01: "Met Gurney",
    0x04: "Find Prospectors",
    0x08: "Prospectors Found",
    0x0C: "Found Communications",
    0x10: "Found Harvester",
    0x14: "Post-Harvester",
    0x18: "Ecology Intro",
    0x1C: "Water Discovery",
    0x20: "Mid-Game",
    0x24: "Sietch Tuek",
    0x28: "Pre-Stilgar",
    0x2C: "Take Stilgar",
    0x30: "Post-Stilgar",
    0x35: "Leto Left",
    0x38: "Harkonnen Push",
    0x3C: "Resistance",
    0x40: "Counter-Attack",
    0x48: "Pre-Worm Riding",
    0x4F: "Can Worm-Ride",
    0x50: "Rode Worm",
    0x58: "Army Building",
    0x60: "Find Chani",
    0x64: "Chani Kidnapped",
    0x68: "Chani Returned",
    0xC8: "Ending / Victory",
}


# =============================================================================
# TROOP JOB CODES
# =============================================================================

TROOP_JOBS = {
    0: "None/Idle",
    1: "Spice Mining",
    2: "Spice Mining (alt)",
    3: "Military Training",
    4: "Military (Army)",
    5: "Ecology (Vegetation)",
    6: "Equipment Manufacturing",
    7: "Spice Prospecting",
    8: "Espionage",
}


# =============================================================================
# EQUIPMENT FLAGS (bitfield)
# =============================================================================

EQUIPMENT_FLAGS = {
    0x01: "Knives",
    0x02: "Krysknives",
    0x04: "LaserGuns",
    0x08: "Weirding",
    0x10: "Atomics",
    0x20: "Bulbs",
    0x40: "Harvesters",
    0x80: "Ornis",
}


def equipment_str(val: int) -> str:
    """Convert equipment bitfield to human-readable string."""
    parts = [name for bit, name in EQUIPMENT_FLAGS.items() if val & bit]
    return ', '.join(parts) if parts else 'None'


# =============================================================================
# CONDIT VM OPERATION CODES
# =============================================================================

CONDIT_OPS = {
    0x00: ("EQ",  "==",  "dx == ax → 0xFFFF, else 0"),
    0x01: ("LT",  "<u",  "dx < ax unsigned → 0xFFFF, else 0"),
    0x02: ("GT",  ">u",  "dx > ax unsigned → 0xFFFF, else 0"),
    0x03: ("NE",  "!=",  "dx != ax → 0xFFFF, else 0"),
    0x04: ("LE",  "<=s", "dx <= ax signed → 0xFFFF, else 0"),
    0x05: ("GE",  ">=s", "dx >= ax signed → 0xFFFF, else 0"),
    0x06: ("ADD", "+",   "dx = dx + ax"),
    0x07: ("SUB", "-",   "dx = dx - ax"),
    0x08: ("AND", "&",   "dx = dx & ax"),
    0x09: ("OR",  "|",   "dx = dx | ax"),
}

# Known DS-segment variables referenced by CONDIT bytecodes
CONDIT_VARIABLES = {
    0x0002: "ElapsedTime",    # uint16: bits[3:0]=hour, bits[15:4]=day
    0x002A: "GameStage",      # uint8: master story progression
    0x00FC: "var_FC",         # frequently referenced, purpose TBD
}


# =============================================================================
# CRYOGENIC ENGINE ADDRESSES
# =============================================================================

DS_VARIABLES = {
    0x0000: ("uint16", "unknown_0000",               "0x441E area in save"),
    0x0002: ("uint16", "GameElapsedTime",             "0x5592 in save"),
    0x002A: ("byte",   "GameStage",                   "0x4448 in save"),
    0x00FC: ("byte",   "var_FC",                      "frequently used in CONDIT"),
    0x144C: ("byte",   "loadedSalIndex",              "runtime only"),
    0x21DA: ("uint16", "OffsetToMenuType",            "runtime only"),
    0x2570: ("uint16", "MapClickHandlerAddress",      "runtime only"),
    0x4772: ("uint16", "TimeBetweenFaceZooms",        "runtime only"),
    0x47A8: ("byte",   "DialogueCounter",             "runtime only"),
    0x47F8: ("bytes",  "salStackBuffer[24]",          "runtime only, cleared 0xFF"),
    0x4854: ("uint16", "SceneSequenceOffset",         "runtime only"),
    0xAA72: ("dword",  "resConditOffset",             "runtime only"),
    0xCE78: ("uint16", "resourceIndex",               "runtime only"),
    0xCEEB: ("byte",   "languageSetting",             "runtime only"),
    0xDBB0: ("dword",  "spriteSheetResourcePointer",  "runtime only"),
}

CS1_FUNCTIONS = {
    0x093F: "LoadSceneSequenceData",
    0x0945: "SetSceneSequenceOffset",
    0x1AD1: "GetSunlightDay",
    0x1AE0: "SetHourOfTheDayToAX",
    0x2D74: "open_SAL_resource",
    0x3B59: "draw_SAL",
    0x3BE9: "SAL_polygon",
    0x5E4F: "calc_SAL_index",
    0xA1E8: "IncDialogueCounter",
    0xC1DB: "CONDIT_ReadOperand",
    0xC204: "CONDIT_DispatchOp",
    0xC22F: "draw_sprite",
    0xC266: "CONDIT_Evaluate",
    0xC85B: "InitDialogue",
    0xF0B9: "open_resource_by_index_si",
    0xF0D6: "read_and_maybe_hsq",
}
