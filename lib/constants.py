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
# NPC DATA (save offset 0x53F4)
# =============================================================================

NPC_COUNT = 16
NPC_SIZE  = 8       # 8 data bytes per NPC
NPC_PAD   = 8       # 8 padding bytes (zeros)
NPC_STRIDE = NPC_SIZE + NPC_PAD   # 16 bytes total per NPC record

# NPC record field offsets (within each 16-byte record)
NPC_FIELDS = {
    0: ("SpriteId",           "byte",  "Sprite/character identifier"),
    1: ("FieldB",             "byte",  "Unknown (Field B)"),
    2: ("RoomLocation",       "byte",  "Room/sietch location index"),
    3: ("TypeOfPlace",        "byte",  "Type of place (palace room, sietch, etc.)"),
    4: ("DialogueAvailable",  "byte",  "Dialogue availability flags (Field E)"),
    5: ("ExactPlace",         "byte",  "Exact place within location"),
    6: ("ForDialogue",        "byte",  "DIALOGUE.HSQ entry index for this NPC"),
    7: ("FieldH",             "byte",  "Unknown (Field H)"),
}

# Sprite ID → character name (from DuneEdit2/ODRADE)
NPC_SPRITES = {
    0x00: "Unused/Empty",
    0x01: "Duke Leto Atreides",
    0x02: "Jessica Atreides",
    0x03: "Thufir Hawat",
    0x04: "Duncan Idaho",
    0x05: "Gurney Halleck",
    0x06: "Stilgar",
    0x07: "Liet Kynes",
    0x08: "Chani",
    0x09: "Harah",
    0x0A: "Baron Vladimir Harkonnen",
    0x0B: "Feyd-Rautha Harkonnen",
    0x0C: "Emperor Shaddam IV",
    0x0D: "Harkonnen Captain",
    0x0E: "Smuggler",
    0x0F: "Fremen Chief (type 1)",
    0x10: "Fremen Chief (type 2)",
}


# =============================================================================
# SMUGGLER DATA (save offset 0x54F6)
# =============================================================================

SMUGGLER_COUNT = 6
SMUGGLER_SIZE  = 14     # 14 data bytes per smuggler
SMUGGLER_PAD   = 3      # 3 padding bytes
SMUGGLER_STRIDE = SMUGGLER_SIZE + SMUGGLER_PAD  # 17 bytes total

# Smuggler record field offsets
SMUGGLER_FIELDS = {
    0:  ("Region",              "byte",  "Map region where smuggler operates"),
    1:  ("WillingnessToHaggle", "byte",  "Haggle willingness (higher=easier)"),
    2:  ("FieldC",              "byte",  "Unknown (Field C)"),
    3:  ("FieldD",              "byte",  "Unknown (Field D)"),
    4:  ("Harvesters",          "byte",  "Harvesters in stock"),
    5:  ("Ornithopters",        "byte",  "Ornithopters in stock"),
    6:  ("KrysKnives",          "byte",  "Krysknives in stock"),
    7:  ("LaserGuns",           "byte",  "Laser guns in stock"),
    8:  ("WeirdingModules",     "byte",  "Weirding modules in stock"),
    9:  ("HarvestersPrice",     "byte",  "Harvesters price"),
    10: ("OrnithoptersPrice",   "byte",  "Ornithopters price"),
    11: ("KrysKnivesPrice",     "byte",  "Krysknives price"),
    12: ("LaserGunsPrice",      "byte",  "Laser guns price"),
    13: ("WeirdingModulesPrice","byte",  "Weirding modules price"),
}


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
    0x0002: "GameElapsedTime",  # uint16: bits[3:0]=hour(0-15), bits[15:4]=day
    0x000A: "MapFlags",         # byte: bit 0 tested, bit 3 set; map display flags
    0x000B: "SietchTroopCount", # byte: compared with 8; troop count at current sietch
    0x0010: "SietchBitfield1",  # uint16: sietch capability flags
    0x0012: "SietchBitfield2",  # uint16: sietch status bitfield
    0x0023: "DialogueChoiceState",  # byte: dialogue tree position
    0x0025: "SpiceShipmentCarry",   # byte: spice shipment tracking
    0x0026: "SpiceShipmentFlag",    # byte: 0 or 0xFF; spice shipment pending
    0x002A: "GameStage",        # byte: master story progression (0x00-0xC8)
    0x002B: "GameStageChanged", # byte: flag; stage just changed
    0x0090: "NPCEncounterCounter",  # byte: NPC encounter logic counter
    0x00BF: "BattleFlags",     # byte: battle state flags (bits 1,2,4,6,0x10,0x20,0x80)
    0x00C2: "BattlePhase",     # byte: compared with 0,7; battle phase
    0x00C8: "HarkonnenStrength",# byte: Harkonnen military strength
    0x00EA: "EventNPCId",      # byte: 0xFF=none, 0x0E checked; active event NPC
    0x00F4: "DayNightPhase",   # byte: day/night cycle phase
    0x00FB: "WormSignFlag",    # byte: negated, compared with 0; worm activity
    0x00FC: "ConditVarFC",     # byte: frequently referenced; condition result cache?
}


# =============================================================================
# DS-SEGMENT VARIABLE MAP (comprehensive)
#
# All offsets relative to DS:0x0000 (runtime DS=0x1138, linear 0x11380).
# ASM address conversion: DS_offset = ASM_linear - 0x1F4B0
#
# Sources:
#   [C] = Cryogenic/Spice86 GlobalsOnDs.cs (auto-generated getters)
#   [X] = Cryogenic ExtraGlobalsOnDs.cs / Overrides (manually named)
#   [A] = OpenRakis DNCDPRG_RECENT.ASM (IDA disassembly labels)
#   [S] = Save file mapping (decompressed offset in DUNE*.SAV)
#   [D] = DuneEdit2 offset definitions
#
# Format: offset: (type, name, description)
# =============================================================================

DS_VARIABLES = {
    # =========================================================================
    # GAME STATE BLOCK (0x0000 - 0x0115)
    # These variables are part of the core game state; many map to save offsets.
    # In-memory DS offsets can be converted to save offsets by adding the base
    # of the game state block within the save file.
    # =========================================================================

    # --- Time & Core State (0x00-0x0F) ---
    0x0000: ("uint16", "GameStateFlags",            "[C] word; rol'd to shift bits; save 0x441E area"),
    0x0002: ("uint16", "GameElapsedTime",           "[C,A,S] bits[3:0]=hour(0-15), bits[15:4]=day; save 0x5592"),
    0x0004: ("uint16", "PlayerPosition",            "[C] byte+word access; position/coords; ds:4 read frequently"),
    0x0005: ("byte",   "PlayerPositionHi",          "[C] high byte of position word"),
    0x0006: ("uint16", "CurrentLocationId",         "[C] byte+word; compared with BX; current sietch/location"),
    0x0007: ("byte",   "CurrentLocationHi",         "[C] high byte / sub-location"),
    0x0008: ("byte",   "PlayerState",               "[C] compared with 0xFF; player state/mode flag"),
    0x0009: ("byte",   "RegionId",                  "[C] compared with BH; current map region"),
    0x000A: ("byte",   "MapFlags",                  "[C] bit 0 tested, bit 3 set; map display flags"),
    0x000B: ("byte",   "SietchTroopCount",          "[C] compared with 8; troop count at current sietch"),
    0x000C: ("byte",   "var_0C",                    "[C] written by init code"),
    0x000D: ("byte",   "var_0D",                    "[C] written by init code"),
    0x000E: ("uint16", "var_0E",                    "[C] word; written by init code"),

    # --- Sietch Management Flags (0x10-0x1B) --- [PREVIOUSLY UNMAPPED]
    0x0010: ("uint16", "SietchBitfield1",           "[C,A] word; bits tested (8,0x10); AND/OR'd; sietch capability flags"),
    0x0012: ("uint16", "SietchBitfield2",           "[C,A] word; bits tested (8,0x80,0x1000); sietch status bitfield"),
    0x0014: ("uint16", "SietchMapCoords",           "[C,A] word; OR'd with ax; map coordinates or flags"),
    0x0016: ("uint16", "SietchRegionData",          "[C,A] word; set during sietch processing"),
    0x0018: ("byte",   "SietchTroopLink",           "[C,A] byte; set during sietch iteration; troop linked list"),
    0x0019: ("byte",   "SietchSpiceDensity",        "[C,A] byte; set to 0 or 0xFF; spice availability"),
    0x001A: ("byte",   "SietchIterCounter",         "[C,A] byte; incremented in loops; iterator for sietch processing"),
    0x001B: ("byte",   "SietchFieldB",              "[C,A] byte; incremented in sietch code"),

    # --- NPC/Dialogue Tracking (0x1C-0x23) ---
    0x001C: ("byte",   "NPCInteractionState1",      "[A] set during NPC/location processing"),
    0x001D: ("byte",   "NPCInteractionState2",      "[A] set during NPC/location processing"),
    0x001E: ("byte",   "NPCInteractionState3",      "[A] set during NPC/location processing"),
    0x001F: ("byte",   "NPCInteractionState4",      "[A] set to 0 or computed value"),
    0x0020: ("uint16", "NPCActionAccumulator",      "[A] word; set, added to; accumulates NPC action data"),
    0x0022: ("byte",   "NPCActionCounter",          "[A] inc/dec'd; counts NPC interactions"),
    0x0023: ("byte",   "DialogueChoiceState",       "[C,A] compared with 0,3,4,0x11,0x64; dialogue tree position"),
    0x0024: ("byte",   "HarkonnenAttackState",      "[A] compared with 0x0C; Harkonnen military state"),

    # --- Game Progression Flags (0x25-0x2B) --- [PREVIOUSLY UNMAPPED 0x25-0x26]
    0x0025: ("byte",   "SpiceShipmentCarry",        "[A] ADC'd (add with carry); spice shipment tracking"),
    0x0026: ("byte",   "SpiceShipmentFlag",         "[C,A] set to 0 or 0xFF; spice shipment pending flag"),
    0x0028: ("byte",   "var_28",                    "[C] byte; written"),
    0x0029: ("byte",   "var_29",                    "[C] byte; written"),
    0x002A: ("byte",   "GameStage",                 "[C,A,S] master story progression (0x00-0xC8); save 0x4448"),
    0x002B: ("byte",   "GameStageChanged",          "[C,A] compared with 0; flag: stage just changed"),
    0x002C: ("uint16", "SietchTargetPtr",           "[C,A] word; set with DI; pointer to target sietch data"),
    0x002E: ("byte",   "SietchTargetField1",        "[C,A] set during sietch targeting"),
    0x002F: ("byte",   "SietchTargetField2",        "[C,A] set during sietch targeting"),
    0x0030: ("byte",   "SietchTargetField3",        "[A] set during sietch targeting"),
    0x0031: ("byte",   "var_31",                    "[C] byte"),

    # --- Map/Region Working Data (0x32-0x3C) ---
    0x0032: ("uint16", "var_32",                    "[C] word"),
    0x0034: ("uint16", "var_34",                    "[C] word"),
    0x0036: ("byte",   "var_36",                    "[C] byte"),
    0x0037: ("byte",   "var_37",                    "[C] byte"),
    0x0038: ("byte",   "var_38",                    "[C] byte"),
    0x0039: ("byte",   "var_39",                    "[C] byte"),
    0x003A: ("byte",   "var_3A",                    "[C] byte"),
    0x003B: ("byte",   "var_3B",                    "[C] byte"),
    0x003C: ("byte",   "var_3C",                    "[C] byte"),

    # --- Sietch/Troop Working Registers (0x40-0x54) ---
    0x0040: ("byte",   "TroopWorkingId",            "[C,A] byte; set during troop iteration"),
    0x0041: ("byte",   "TroopWorkingField",         "[C,A] byte; troop field being processed"),
    0x0042: ("uint16", "TroopWorkingCoords",        "[C,A] word; exchanged, set; troop coordinates"),
    0x0044: ("uint16", "TroopWorkingData1",         "[C,A] word; set during troop processing"),
    0x0046: ("uint16", "TroopWorkingData2",         "[C,A] word; set during troop processing"),
    0x0048: ("uint16", "TroopWorkingData3",         "[C,A] word; set during troop processing"),
    0x004A: ("uint16", "TroopWorkingData4",         "[A] word; set from troop field"),
    0x004C: ("byte",   "InSietchFlag",              "[C,A] 0x00 or 0xFF; whether player is inside a sietch"),
    0x004D: ("byte",   "TroopWorkingJob",           "[C,A] byte; set during troop iteration"),
    0x004E: ("uint16", "TroopWorkingPopulation",    "[C,A] word; troop population"),
    0x0050: ("byte",   "TroopWorkingSkill1",        "[C,A] byte; spice/army skill"),
    0x0051: ("byte",   "TroopWorkingSkill2",        "[C,A] byte; army/ecology skill"),
    0x0052: ("byte",   "TroopWorkingSkill3",        "[C,A] byte; ecology skill"),
    0x0053: ("byte",   "TroopWorkingMotivation",    "[C,A] byte; motivation"),
    0x0054: ("byte",   "TroopWorkingEquipment",     "[C,A] byte; equipment bitfield"),

    # --- Map Display Coordinates (0x5C-0x61) ---
    0x005C: ("uint16", "MapViewportX",              "[C,A] word; OR'd with ax; map viewport X"),
    0x005E: ("uint16", "MapViewportY",              "[C,A] word; OR'd with ax; map viewport Y"),
    0x0060: ("byte",   "MapZoomLevel",              "[C,A] byte; map zoom/scale"),
    0x0061: ("byte",   "MapDisplayMode",            "[C] byte; display mode flag"),

    # --- Wind/Weather (0x7E-0x7F) ---
    0x007E: ("byte",   "WindDirection",             "[C] byte"),
    0x007F: ("byte",   "WindSpeed",                 "[C] byte"),

    # --- NPC Encounter/Movement (0x90-0x9F) --- [PREVIOUSLY UNMAPPED]
    0x0090: ("byte",   "NPCEncounterCounter",       "[C,A] byte; incremented during NPC encounter logic"),
    0x0091: ("byte",   "NPCEncounterField1",        "[C,A] byte; set during NPC encounter"),
    0x0092: ("byte",   "NPCEncounterField2",        "[C,A] byte; set during NPC encounter"),
    0x0094: ("uint16", "NPCMovementX",              "[C] word; NPC position/movement X"),
    0x0096: ("uint16", "NPCMovementY",              "[C] word; NPC position/movement Y"),
    0x0098: ("uint16", "NPCMovementDX",             "[C] word; NPC movement delta X"),
    0x009A: ("uint16", "NPCMovementDY",             "[C] word; NPC movement delta Y"),
    0x009C: ("byte",   "NPCMovementFlags",          "[C] byte"),
    0x009D: ("byte",   "SietchDiscoverCounter",     "[A] set to 0, xchg'd, tracked; sietch discovery counter"),
    0x009E: ("byte",   "SietchDiscoverFlags",       "[A] OR'd with 0x10; inc'd, AND'd with 3"),
    0x009F: ("byte",   "SietchDiscoverRegion",      "[C,A] set to 0,1,2,3; compared; region being discovered"),
    0x00A0: ("uint16", "SietchProcessingPtr",       "[C,A] word; read, subtracted from; sietch data pointer"),
    0x00A2: ("uint16", "var_A2",                    "[C] word"),
    0x00A4: ("uint16", "var_A4",                    "[C] word"),
    0x00A6: ("uint16", "SietchWorkX",               "[C,A] word; set from xchg; sietch working X coord"),
    0x00A8: ("uint16", "SietchWorkDistance",         "[C,A] word; set from CX; distance calculation"),
    0x00AA: ("uint16", "var_AA",                    "[C] word"),
    0x00AC: ("uint16", "var_AC",                    "[C] word"),
    0x00AE: ("uint16", "SietchWorkY",               "[A] xchg'd with A6; sietch working Y coord"),
    0x00B0: ("uint16", "SietchWorkBX",              "[A] set from BX"),
    0x00B2: ("uint16", "SietchWorkDiff",            "[A] computed difference"),

    # --- Harkonnen/Battle System (0xBC-0xDB) ---
    0x00BC: ("uint16", "BattleTargetPtr",           "[A] word; set from DX; battle target data"),
    0x00BE: ("byte",   "BattleEnemyCount",          "[A] byte; compared with 0; set; enemy count"),
    0x00BF: ("byte",   "BattleFlags",               "[C,A] bits tested/set (1,2,4,6,0x10,0x20,0x80,0x90); battle state flags"),
    0x00C0: ("uint16", "BattleForceCount",          "[A] word; set to 0, set from AX"),
    0x00C2: ("byte",   "BattlePhase",               "[C,A] compared with 0,7; incremented; battle phase"),
    0x00C3: ("byte",   "BattleTurnCounter",         "[A] incremented, read; battle turn counter"),
    0x00C4: ("byte",   "BattleProgressCounter",     "[A] incremented; attack progress"),
    0x00C5: ("byte",   "var_C5",                    "[C] byte"),
    0x00C6: ("byte",   "var_C6",                    "[C] byte"),
    0x00C8: ("byte",   "HarkonnenStrength",         "[A] inc/dec'd; compared; Harkonnen military strength"),
    0x00C9: ("byte",   "HarkonnenReserves",         "[A] inc/dec'd; dec'd when C8 changes; Harkonnen reserves"),
    0x00CA: ("uint16", "var_CA",                    "[C] word"),
    0x00CC: ("uint16", "var_CC",                    "[C] word"),
    0x00CF: ("byte",   "ConversationNPCId",         "[C,A] set; NPC being spoken to"),
    0x00D0: ("uint16", "var_D0",                    "[C] word"),
    0x00D5: ("byte",   "LastGameStage",             "[A] xchg'd/compared with ds:2Ah; previous stage tracker"),
    0x00D6: ("uint16", "var_D6",                    "[C] word"),
    0x00DB: ("byte",   "HarkonnenAttackPattern",    "[A] XOR'd with C8; attack pattern byte"),
    0x00DC: ("uint16", "BattleTimer1",              "[C,A] compared with 0x1E; battle timing"),
    0x00DE: ("uint16", "BattleTimer1Alt",           "[A] loaded into BP alongside DC"),
    0x00E2: ("uint16", "BattleTimer2",              "[C,A] compared with 0x1E; battle timing"),
    0x00E4: ("uint16", "BattleTimer2Alt",           "[A] loaded into BP alongside E2"),

    # --- Event/Dialogue Triggers (0xE7-0xFF) ---
    0x00E7: ("byte",   "var_E7",                    "[C] byte"),
    0x00E8: ("byte",   "EventTriggerTimer",         "[C,A] compared with 0x0A, incremented; event timing counter"),
    0x00E9: ("byte",   "EventNPCParam1",            "[A] set during event processing"),
    0x00EA: ("byte",   "EventNPCId",                "[C,A] compared with 0xFF,0x0E; set to 0xFF; active event NPC"),
    0x00EB: ("byte",   "EventNPCParam2",            "[A] set from C9; event NPC parameter"),
    0x00ED: ("byte",   "TroopMovementState",        "[A] set during troop movement"),
    0x00EE: ("uint16", "TroopMovementTarget",       "[A] word; set to 0; movement target"),
    0x00F0: ("uint16", "var_F0",                    "[C] word"),
    0x00F2: ("uint16", "MessageDisplayPtr",         "[A] word; set; pointer to message data"),
    0x00F4: ("byte",   "DayNightPhase",             "[C,A] read, copied to F5; day/night cycle phase"),
    0x00F5: ("byte",   "DayNightPhasePrev",         "[C,A] set from F4; previous phase for change detection"),
    0x00F6: ("byte",   "var_F6",                    "[C] byte"),
    0x00F7: ("byte",   "var_F7",                    "[C] byte"),
    0x00F8: ("byte",   "DiscoveryProgress",         "[A] inc/dec'd; discovery/exploration progress"),
    0x00F9: ("byte",   "DiscoverySpeedMod",         "[A] added 8 to; speed modifier for discovery"),
    0x00FA: ("byte",   "var_FA",                    "[C] byte"),
    0x00FB: ("byte",   "WormSignFlag",              "[C,A] negated, compared with 0; worm sign / worm activity flag"),
    0x00FC: ("byte",   "ConditVarFC",               "[C] frequently used in CONDIT VM; condition result cache?"),
    0x00FD: ("byte",   "var_FD",                    "[C] byte"),
    0x00FE: ("byte",   "PrevGameStageSwap",         "[A] xchg'd with ds:2Ah; previous game stage (swap register)"),
    0x00FF: ("byte",   "StageChangeCounter",        "[A] set to 0 then inc'd; stage transition counter"),

    # --- Extended State (0x0115) ---
    0x0115: ("byte",   "var_0115",                  "[C] byte"),

    # =========================================================================
    # RESOURCE / SCENE MANAGEMENT (0x1000 - 0x1BFF)
    # =========================================================================
    0x101A: ("uint16", "var_101A",                  "[C] word"),
    0x109A: ("uint16", "var_109A",                  "[C] word"),
    0x10AA: ("uint16", "var_10AA",                  "[C] word"),
    0x10BA: ("uint16", "var_10BA",                  "[C] word"),
    0x10CA: ("uint16", "var_10CA",                  "[C] word"),
    0x114E: ("uint16", "var_114E",                  "[C] word"),
    0x1150: ("uint16", "var_1150",                  "[C] word"),
    0x1152: ("uint16", "var_1152",                  "[C] byte+word access"),
    0x1153: ("byte",   "var_1153",                  "[C] byte"),
    0x1154: ("uint16", "var_1154",                  "[C] word"),
    0x115A: ("uint16", "var_115A",                  "[C] word"),
    0x115C: ("uint16", "var_115C",                  "[C] word"),
    0x1170: ("uint16", "var_1170",                  "[C] word"),
    0x1172: ("uint16", "var_1172",                  "[C] word"),
    0x1174: ("uint16", "var_1174",                  "[C] word"),
    0x1176: ("uint16", "var_1176",                  "[C] word"),
    0x118D: ("uint16", "var_118D",                  "[C] word"),
    0x1190: ("byte",   "var_1190",                  "[C] byte"),
    0x11BB: ("byte",   "var_11BB",                  "[C] byte"),
    0x11BD: ("uint16", "var_11BD",                  "[C] word"),
    0x11BF: ("uint16", "var_11BF",                  "[C] word"),
    0x11C5: ("uint16", "var_11C5",                  "[C] word"),
    0x11C7: ("byte",   "var_11C7",                  "[C] byte"),
    0x11C8: ("byte",   "var_11C8",                  "[C] byte"),
    0x11C9: ("byte",   "var_11C9",                  "[C] byte"),
    0x11CA: ("byte",   "OrniMapActiveFlag",         "[C,X] 0=orni liftoff/land, 1=map/dialogue; UI input mode"),
    0x11CB: ("byte",   "var_11CB",                  "[C] byte"),
    0x11CC: ("uint16", "var_11CC",                  "[C] byte+word access"),
    0x11CE: ("uint16", "var_11CE",                  "[C] word"),
    0x11D3: ("uint16", "var_11D3",                  "[C] word"),
    0x11DB: ("uint16", "var_11DB",                  "[C] word"),
    0x11ED: ("uint16", "var_11ED",                  "[C] word"),
    0x11EF: ("uint16", "var_11EF",                  "[C] word"),
    0x11F1: ("uint16", "var_11F1",                  "[C] word"),
    0x11F3: ("uint16", "var_11F3",                  "[C] word"),
    0x11F5: ("uint16", "var_11F5",                  "[C] word"),
    0x11F7: ("uint16", "var_11F7",                  "[C] word"),
    0x11F9: ("uint16", "var_11F9",                  "[C] word"),
    0x11FB: ("uint16", "var_11FB",                  "[C] word"),
    0x11FD: ("uint16", "var_11FD",                  "[C] word"),
    0x11FF: ("uint16", "var_11FF",                  "[C] word"),
    0x120D: ("uint16", "var_120D",                  "[C] word"),
    0x120F: ("uint16", "var_120F",                  "[C] word"),
    0x144C: ("byte",   "LoadedSalIndex",            "[C,A] currently loaded SAL scene index; 0xFF=none"),
    0x146E: ("uint16", "var_146E",                  "[C] word"),
    0x1470: ("bytes",  "RoomTransitionData[8]",     "[X] 8 bytes; copied to D834/D83C on room/scene change"),
    0x149A: ("uint16", "var_149A",                  "[C] word"),
    0x18F2: ("byte",   "var_18F2",                  "[C] byte"),
    0x194A: ("uint16", "var_194A",                  "[C] word"),
    0x194C: ("uint16", "var_194C",                  "[C] word"),
    0x1954: ("uint16", "var_1954",                  "[C] byte+word access"),
    0x1955: ("byte",   "var_1955",                  "[C] byte"),
    0x196A: ("uint16", "var_196A",                  "[C] word"),
    0x196C: ("byte",   "var_196C",                  "[C] byte"),
    0x197C: ("uint16", "var_197C",                  "[C] word"),
    0x197E: ("uint16", "var_197E",                  "[C] word"),
    0x1980: ("uint16", "var_1980",                  "[C] word"),
    0x1982: ("uint16", "var_1982",                  "[C] word"),
    0x1AFE: ("uint16", "var_1AFE",                  "[C] word"),
    0x1B0C: ("uint16", "var_1B0C",                  "[C] word"),
    0x1BE4: ("uint16", "var_1BE4",                  "[C] word"),
    0x1BEA: ("uint16", "CharInRoomAfterDialogue",   "[C,X] 128 after dialogue if char in room; cleared on screen change"),
    0x1BF0: ("uint16", "var_1BF0",                  "[C] word"),
    0x1BF2: ("uint16", "var_1BF2",                  "[C] word"),
    0x1BF8: ("uint16", "CharAfterDialogueFlag",     "[C,X] 128 after dialogue end; cleared on screen change"),
    0x1C06: ("uint16", "PostScreenChangeFlag",      "[C,X] cleared on screen change; when 255=enter palace not orni"),
    0x1C14: ("uint16", "var_1C14",                  "[C] word"),
    0x1C22: ("uint16", "var_1C22",                  "[C] word"),
    0x1C30: ("byte",   "var_1C30",                  "[C] byte"),
    0x1CC4: ("byte",   "var_1CC4",                  "[C] byte"),
    0x1F11: ("byte",   "var_1F11",                  "[C] byte"),
    0x1F12: ("uint16", "var_1F12",                  "[C] word"),

    # =========================================================================
    # UI / MENU SYSTEM (0x2100 - 0x22FF)
    # =========================================================================
    0x2110: ("uint16", "var_2110",                  "[C] word"),
    0x2115: ("byte",   "var_2115",                  "[C] byte"),
    0x2119: ("byte",   "var_2119",                  "[C] byte"),
    0x21DA: ("uint16", "OffsetToMenuType",          "[C,X] indirect ptr; menu type determines UI actions"),
    0x21FD: ("byte",   "var_21FD",                  "[C] byte"),
    0x2222: ("uint16", "var_2222",                  "[C] word"),
    0x2224: ("uint16", "var_2224",                  "[C] word"),
    0x222C: ("uint16", "var_222C",                  "[C] word"),
    0x2234: ("uint16", "var_2234",                  "[C] word"),
    0x2240: ("uint16", "var_2240",                  "[C] word"),
    0x2244: ("uint16", "var_2244",                  "[C] word"),
    0x2246: ("uint16", "var_2246",                  "[C] word"),
    0x224A: ("uint16", "var_224A",                  "[C] word"),
    0x2254: ("uint16", "var_2254",                  "[C] word"),
    0x2256: ("uint16", "var_2256",                  "[C] word"),
    0x226D: ("byte",   "var_226D",                  "[C] byte"),
    0x227D: ("byte",   "var_227D",                  "[C] byte"),
    0x227E: ("uint16", "var_227E",                  "[C] word"),
    0x22A6: ("uint16", "var_22A6",                  "[C] word"),
    0x22D9: ("uint16", "var_22D9",                  "[C] word"),
    0x22DB: ("uint16", "var_22DB",                  "[C] word"),
    0x22DD: ("uint16", "var_22DD",                  "[C] word"),
    0x22DF: ("uint16", "var_22DF",                  "[C] word"),
    0x22E3: ("byte",   "var_22E3",                  "[C] byte"),
    0x22FC: ("uint16", "var_22FC",                  "[C] word"),
    0x2406: ("uint16", "var_2406",                  "[C] word"),
    0x243E: ("uint16", "var_243E",                  "[C] word"),
    0x2460: ("uint16", "var_2460",                  "[C] word"),

    # =========================================================================
    # FONT / INPUT / MAP HANDLERS (0x2500 - 0x2950)
    # =========================================================================
    0x2514: ("uint16", "var_2514",                  "[C] word"),
    0x2516: ("uint16", "var_2516",                  "[C] word"),
    0x2518: ("uint16", "FontRenderAddress",         "[C,X] font rendering code address; set per font type"),
    0x2570: ("uint16", "MapClickHandlerAddress",    "[C,X] address of click handler for current map view"),
    0x2580: ("uint16", "MousePosScalerX",           "[C,A] mouse position X scaler; byte+word access"),
    0x2581: ("byte",   "MousePosScalerY",           "[C] mouse position Y scaler"),
    0x2582: ("uint16", "MouseCursorImageAddr",      "[C,A] address of mouse cursor image data"),
    0x2772: ("uint16", "var_2772",                  "[C] word"),
    0x2784: ("uint16", "ResourceId",                "[C,A] current resource ID being loaded; 0xFFFF=none"),
    0x2786: ("uint16", "var_2786",                  "[C] word"),
    0x2788: ("byte",   "BookMirrorCounter",         "[C,X] incremented at book/mirror; reset on game load/orni land"),
    0x2882: ("uint16", "AudioTimeSamplesHi",        "[A] high word of audio timing (28224 samples)"),
    0x2884: ("uint16", "AudioTimeSamplesLo",        "[A] low word of audio timing (28224 samples)"),
    0x2886: ("uint16", "var_2886",                  "[C] word"),
    0x2888: ("uint16", "var_2888",                  "[C] word"),
    0x288E: ("byte",   "var_288E",                  "[C] byte"),
    0x2896: ("byte",   "var_2896",                  "[C] byte"),
    0x289E: ("byte",   "var_289E",                  "[C] byte"),
    0x28A6: ("byte",   "var_28A6",                  "[C] byte"),
    0x28AE: ("byte",   "var_28AE",                  "[C] byte"),
    0x28BE: ("byte",   "var_28BE",                  "[C] byte"),
    0x28C7: ("uint16", "var_28C7",                  "[C] word"),
    0x28C9: ("uint16", "var_28C9",                  "[C] word"),
    0x28E7: ("byte",   "var_28E7",                  "[C,A] byte; set during init"),
    0x28E8: ("byte",   "var_28E8",                  "[C] byte"),
    0x2913: ("uint16", "InterruptTable",            "[A] interrupt vector table base"),
    0x2941: ("byte",   "var_2941",                  "[C] byte"),
    0x2942: ("byte",   "CmdArgs",                   "[C,A] command line flags; bit 1=MON (monotone)"),
    0x2943: ("byte",   "CmdArgsMemory",             "[C,A] memory manager flags; bit 4 tested"),
    0x2944: ("byte",   "CmdArgsAudio",              "[C,A] audio driver flags"),

    # =========================================================================
    # SYSTEM / LOW-LEVEL (0x3400 - 0x3CBC)
    # =========================================================================
    0x3403: ("byte",   "var_3403",                  "[C] byte"),
    0x35A6: ("uint16", "HnmFileHandle",             "[C,A] HNM video file handle / AnimateMenuUnneeded flag"),
    0x37E2: ("byte",   "var_37E2",                  "[C] byte"),
    0x3810: ("byte",   "var_3810",                  "[C] byte"),
    0x3811: ("dword",  "PcmVocResourceOffset",      "[A] PCM VOC audio resource file offset"),
    0x3813: ("uint16", "var_3813",                  "[C] word"),
    0x3815: ("uint16", "PcmResRemaining",           "[A] bytes remaining in PCM resource"),
    0x3817: ("uint16", "PcmCallbackFlag1",          "[A] PCM callback state flag 1"),
    0x381B: ("uint16", "var_381B",                  "[C] word"),
    0x381F: ("uint16", "PcmCallbackFlag2",          "[A] PCM callback state flag 2"),
    0x3821: ("uint16", "ResFileHandle",             "[C,A] currently open resource file DOS handle"),
    0x376A: ("byte",   "AudioCurrentSfxId",         "[A] current sound effect ID; 0xFF=none"),
    0x38A6: ("uint16", "var_38A6",                  "[C] word"),
    0x38AF: ("byte",   "var_38AF",                  "[C] byte"),

    # =========================================================================
    # GFX VTABLE (0x38B5 - 0x3965)
    # =========================================================================
    0x38B5: ("dword",  "GfxVtable00_SetMode",       "[C] VGA driver vtable entry 0: set video mode"),
    0x38B9: ("dword",  "GfxVtable01_GetInfo",        "[C] vtable 1: get info in AX/CX/BP"),
    0x38BD: ("dword",  "GfxVtable02",                "[C] vtable 2"),
    0x38C1: ("dword",  "GfxVtable03_DrawMouseCursor","[C] vtable 3: draw mouse cursor"),
    0x38C5: ("dword",  "GfxVtable04_RestoreUnderMouse","[C] vtable 4: restore image under mouse"),
    0x38C9: ("dword",  "GfxVtable05_Blit",           "[C] vtable 5: blit operation"),
    0x38CD: ("dword",  "GfxVtable06",                "[C] vtable 6"),
    0x38D1: ("dword",  "GfxVtable07",                "[C] vtable 7"),
    0x38D5: ("dword",  "GfxVtable08_FillZero64000",  "[C] vtable 8: fill 64000 bytes with zero at ES"),
    0x38D9: ("dword",  "GfxVtable09",                "[C] vtable 9"),
    0x38DD: ("dword",  "GfxVtable10",                "[C] vtable 10"),
    0x38ED: ("dword",  "GfxVtable14_CopySquare",     "[C] vtable 14: copy square of pixels, SI=source seg"),
    0x38FB: ("uint16", "var_38FB",                   "[C] word"),
    0x38FD: ("dword",  "GfxVtable18",                "[C] vtable 18"),
    0x3901: ("dword",  "GfxVtable19",                "[C] vtable 19"),
    0x3905: ("dword",  "GfxVtable20_NoOp",           "[C] vtable 20: no operation"),
    0x390D: ("dword",  "GfxVtable22",                "[C] vtable 22"),
    0x3915: ("dword",  "GfxVtable24",                "[C] vtable 24"),
    0x3919: ("dword",  "GfxVtable25",                "[C] vtable 25"),
    0x391D: ("dword",  "GfxVtable26",                "[C] vtable 26"),
    0x3925: ("dword",  "GfxVtable28",                "[C] vtable 28"),
    0x3929: ("dword",  "GfxVtable29",                "[C] vtable 29"),
    0x392D: ("dword",  "GfxVtable30",                "[C] vtable 30"),
    0x3935: ("dword",  "GfxVtable32",                "[C] vtable 32"),
    0x3939: ("dword",  "GfxVtable33_UpdateVgaOffset","[C] vtable 33: update VGA offset from line number AX"),
    0x3945: ("dword",  "GfxVtable36",                "[C] vtable 36"),
    0x394D: ("dword",  "GfxVtable38",                "[C] vtable 38"),
    0x3951: ("dword",  "GfxVtable39",                "[C] vtable 39"),
    0x3959: ("dword",  "GfxVtable41_CopyPalette",    "[C] vtable 41: copy palette2 to palette1"),
    0x395D: ("dword",  "GfxVtable42",                "[C] vtable 42"),
    0x396D: ("dword",  "var_396D",                   "[C] dword"),
    0x3975: ("dword",  "var_3975",                   "[C] dword"),
    0x3977: ("uint16", "var_3977",                   "[C] word"),
    0x3985: ("dword",  "var_3985",                   "[C] dword"),

    # =========================================================================
    # PCM / AUDIO VTABLE & MEMORY (0x3989 - 0x3CBC)
    # =========================================================================
    0x3989: ("dword",  "PcmVtable1",                "[C,A] PCM audio vtable entry 1"),
    0x398D: ("dword",  "PcmVtable2",                "[C,A] PCM audio vtable entry 2"),
    0x3995: ("dword",  "var_3995",                  "[C] dword"),
    0x3999: ("dword",  "var_3999",                  "[C] dword"),
    0x39A5: ("dword",  "var_39A5",                  "[C] dword"),
    0x39A9: ("uint16", "XmsOrEmsMemLimit",          "[C,A] XMS/EMS memory limit"),
    0x39AB: ("uint16", "JoystickParam",             "[A] joystick parameter"),
    0x39B3: ("uint16", "CmdArgMidi",                "[C,A] MIDI command line argument"),
    0x39B5: ("uint16", "var_39B5",                  "[C] word"),
    0x39B7: ("dword",  "AllocatorNextFreeOffset",   "[C,A] bump allocator: next free offset"),
    0x39B9: ("uint16", "AllocatorNextFreeSegment",  "[C,A] bump allocator: next free segment"),
    0x3CBC: ("uint16", "ErrorMsgPtr",               "[C,A] pointer to error message string"),
    0x3CBE: ("uint16", "var_3CBE",                  "[C] word"),

    # =========================================================================
    # DIALOGUE / SCENE STATE (0x4540 - 0x4854)
    # =========================================================================
    0x4540: ("uint16", "var_4540",                  "[C] word"),
    0x46D2: ("uint16", "var_46D2",                  "[C] word"),
    0x46D4: ("uint16", "var_46D4",                  "[C] word"),
    0x46D6: ("byte",   "var_46D6",                  "[C] byte"),
    0x46D7: ("byte",   "InitClearByte",             "[C,X] byte; cleared to 0 during init"),
    0x46D8: ("byte",   "var_46D8",                  "[C] byte"),
    0x46D9: ("byte",   "var_46D9",                  "[C] byte"),
    0x46DA: ("byte",   "var_46DA",                  "[C] byte"),
    0x46DB: ("uint16", "var_46DB",                  "[C] word"),
    0x46DD: ("byte",   "var_46DD",                  "[C] byte"),
    0x46DE: ("byte",   "var_46DE",                  "[C] byte"),
    0x46DF: ("byte",   "var_46DF",                  "[C] byte"),
    0x46E0: ("byte",   "var_46E0",                  "[C] byte"),
    0x46E1: ("uint16", "var_46E1",                  "[C] word"),
    0x46E3: ("uint16", "MapCopySourceData",         "[C,X] 8 bytes; source for memcopy to DI on map display"),
    0x46E5: ("uint16", "var_46E5",                  "[C] word"),
    0x46E7: ("uint16", "var_46E7",                  "[C] word"),
    0x46E9: ("uint16", "var_46E9",                  "[C] word"),
    0x46EB: ("byte",   "var_46EB",                  "[C] byte"),
    0x46EC: ("byte",   "var_46EC",                  "[C] byte"),
    0x46ED: ("uint16", "var_46ED",                  "[C] word"),
    0x46EF: ("uint16", "var_46EF",                  "[C] word"),
    0x46F1: ("uint16", "var_46F1",                  "[C] word"),
    0x46F3: ("byte",   "var_46F3",                  "[C] byte"),
    0x46F4: ("byte",   "var_46F4",                  "[C] byte"),
    0x46F5: ("byte",   "var_46F5",                  "[C] byte"),
    0x46F6: ("byte",   "var_46F6",                  "[C] byte"),
    0x46F8: ("uint16", "var_46F8",                  "[C] word"),
    0x46FA: ("uint16", "var_46FA",                  "[C] word"),
    0x46FC: ("uint16", "var_46FC",                  "[C] word"),
    0x46FF: ("byte",   "var_46FF",                  "[C] byte"),
    0x4710: ("uint16", "var_4710",                  "[C] word"),
    0x4712: ("uint16", "var_4712",                  "[C] word"),
    0x4720: ("uint16", "var_4720",                  "[C] word"),
    0x4722: ("byte",   "var_4722",                  "[C] byte"),
    0x4723: ("byte",   "var_4723",                  "[C] byte"),
    0x4724: ("byte",   "var_4724",                  "[C] byte"),
    0x4725: ("byte",   "var_4725",                  "[C] byte"),
    0x4726: ("byte",   "var_4726",                  "[C] byte"),
    0x4727: ("byte",   "var_4727",                  "[C] byte"),
    0x4728: ("byte",   "var_4728",                  "[C] byte"),
    0x4729: ("uint16", "var_4729",                  "[C] word"),
    0x472B: ("uint16", "var_472B",                  "[C] word"),
    0x472D: ("uint16", "var_472D",                  "[C] word"),
    0x472F: ("uint16", "var_472F",                  "[C] word"),
    0x4731: ("byte",   "var_4731",                  "[C] byte"),
    0x4732: ("byte",   "var_4732",                  "[C] byte"),
    0x4733: ("uint16", "var_4733",                  "[C] word"),
    0x4735: ("byte",   "var_4735",                  "[C] byte"),
    0x4737: ("byte",   "var_4737",                  "[C] byte"),
    0x4738: ("byte",   "var_4738",                  "[C] byte"),
    0x473B: ("byte",   "var_473B",                  "[C] byte"),
    0x473C: ("uint16", "var_473C",                  "[C] word"),
    0x473E: ("byte",   "var_473E",                  "[C] byte"),
    0x473F: ("dword",  "var_473F",                  "[C] word+dword access"),
    0x4741: ("uint16", "var_4741",                  "[C] word"),
    0x4743: ("uint16", "var_4743",                  "[C] word"),
    0x4745: ("uint16", "var_4745",                  "[C] word"),
    0x4747: ("uint16", "var_4747",                  "[C] word"),
    0x4749: ("uint16", "var_4749",                  "[C] word"),
    0x474B: ("uint16", "var_474B",                  "[C] word"),
    0x474F: ("uint16", "var_474F",                  "[C] word"),
    0x4751: ("byte",   "var_4751",                  "[C] byte"),
    0x4752: ("uint16", "var_4752",                  "[C] word"),
    0x4756: ("uint16", "var_4756",                  "[C] word"),
    0x4758: ("uint16", "var_4758",                  "[C] word"),
    0x476A: ("byte",   "var_476A",                  "[C] byte"),
    0x476B: ("byte",   "var_476B",                  "[C] byte"),
    0x476C: ("byte",   "var_476C",                  "[C] byte"),
    0x476D: ("byte",   "var_476D",                  "[C] byte"),
    0x476E: ("uint16", "DialogueVideoIndex",        "[C,X] set from CE7A (VideoPlayRelatedIndex) in InitDialogue"),
    0x4770: ("uint16", "var_4770",                  "[C] word"),
    0x4772: ("uint16", "TimeBetweenFaceZooms",      "[C,X] set to 0x1770 in InitDialogue; portrait zoom timing"),
    0x4774: ("byte",   "var_4774",                  "[C] byte"),
    0x477C: ("uint16", "var_477C",                  "[C] word"),
    0x477E: ("byte",   "var_477E",                  "[C] byte"),
    0x477F: ("byte",   "var_477F",                  "[C] byte"),
    0x4780: ("uint16", "var_4780",                  "[C] word"),
    0x4782: ("uint16", "var_4782",                  "[C] word"),
    0x4784: ("uint16", "var_4784",                  "[C] word"),
    0x4786: ("uint16", "var_4786",                  "[C] word"),
    0x4788: ("uint16", "var_4788",                  "[C] word"),
    0x478A: ("uint16", "var_478A",                  "[C] word"),
    0x478C: ("byte",   "var_478C",                  "[C] byte"),
    0x478D: ("uint16", "var_478D",                  "[C] word"),
    0x478F: ("uint16", "var_478F",                  "[C] word"),
    0x4791: ("uint16", "var_4791",                  "[C] word"),
    0x4793: ("uint16", "var_4793",                  "[C] word"),
    0x4795: ("uint16", "var_4795",                  "[C] word"),
    0x4797: ("uint16", "var_4797",                  "[C] word"),
    0x4799: ("byte",   "var_4799",                  "[C] byte"),
    0x479A: ("uint16", "var_479A",                  "[C] word"),
    0x479C: ("uint16", "var_479C",                  "[C] word"),
    0x479E: ("uint16", "SkipSceneFlag",             "[C,X] set to 0 on intro skip/book quit; screen garble control"),
    0x47A0: ("uint16", "FontResourceAddress",       "[C,X] font resource data address; set per font type"),
    0x47A2: ("uint16", "var_47A2",                  "[C] word"),
    0x47A4: ("byte",   "var_47A4",                  "[C] byte"),
    0x47A5: ("byte",   "var_47A5",                  "[C] byte"),
    0x47A6: ("byte",   "var_47A6",                  "[C] byte"),
    0x47A7: ("byte",   "var_47A7",                  "[C] byte"),
    0x47A8: ("byte",   "DialogueCounter",           "[C,X] incremented during dialogues; dialogue step tracker"),
    0x47A9: ("byte",   "var_47A9",                  "[C] byte"),
    0x47AA: ("uint16", "var_47AA",                  "[C] word"),
    0x47AC: ("dword",  "var_47AC",                  "[C] word+dword access"),
    0x47AE: ("uint16", "var_47AE",                  "[C] word"),
    0x47B0: ("dword",  "var_47B0",                  "[C] word+dword access"),
    0x47B2: ("uint16", "var_47B2",                  "[C] word"),
    0x47B4: ("uint16", "var_47B4",                  "[C] word"),
    0x47B6: ("dword",  "var_47B6",                  "[C] word+dword access"),
    0x47B8: ("uint16", "var_47B8",                  "[C] word"),
    0x47BA: ("uint16", "var_47BA",                  "[C] word"),
    0x47BC: ("uint16", "var_47BC",                  "[C] word"),
    0x47BE: ("uint16", "var_47BE",                  "[C] word"),
    0x47C2: ("uint16", "var_47C2",                  "[C] byte+word access"),
    0x47C3: ("byte",   "var_47C3",                  "[C] byte"),
    0x47C4: ("uint16", "var_47C4",                  "[C] byte+word access"),
    0x47C6: ("uint16", "var_47C6",                  "[C] word"),
    0x47C8: ("uint16", "var_47C8",                  "[C] word"),
    0x47CA: ("uint16", "var_47CA",                  "[C] word"),
    0x47CE: ("uint16", "var_47CE",                  "[C] word"),
    0x47D0: ("byte",   "var_47D0",                  "[C] byte"),
    0x47D1: ("byte",   "var_47D1",                  "[C] byte"),
    0x47D2: ("uint16", "var_47D2",                  "[C] word"),
    0x47DC: ("byte",   "var_47DC",                  "[C] byte"),
    0x47DD: ("byte",   "var_47DD",                  "[C] byte"),
    0x47DE: ("uint16", "var_47DE",                  "[C] byte+word access"),
    0x47E0: ("byte",   "var_47E0",                  "[C] byte"),
    0x47E1: ("uint16", "var_47E1",                  "[C] byte+word access"),
    0x47E6: ("uint16", "var_47E6",                  "[C] word"),
    0x47E8: ("uint16", "var_47E8",                  "[C] word"),
    0x47EA: ("uint16", "var_47EA",                  "[C] word"),
    0x47EC: ("byte",   "var_47EC",                  "[C] byte"),
    0x47ED: ("byte",   "var_47ED",                  "[C] byte"),
    0x47EE: ("uint16", "var_47EE",                  "[C] word"),
    0x47F0: ("uint16", "var_47F0",                  "[C] word"),
    0x47F2: ("uint16", "var_47F2",                  "[C] word"),
    0x47F4: ("uint16", "var_47F4",                  "[C] word"),
    0x47F6: ("uint16", "SalStackBuffer24b",         "[C,A] SAL stack buffer (24 bytes); scene rendering stack"),
    0x47F8: ("bytes",  "SalStackBufferData[92]",    "[C,X] 92 bytes filled with 0xFF on scene enter/leave"),
    0x4854: ("uint16", "SceneSequenceOffset",       "[C,X,A] current position in scene sequence script"),
    0x487E: ("uint16", "var_487E",                  "[C] word"),
    0x494A: ("uint16", "var_494A",                  "[C] word"),
    0x494C: ("uint16", "var_494C",                  "[C] word"),

    # =========================================================================
    # GAME DATA BUFFERS (0xA5C0 - 0xABFF)
    # =========================================================================
    0xA5C0: ("uint16", "var_A5C0",                  "[C] word"),
    0xA9D0: ("uint16", "var_A9D0",                  "[C] word"),
    0xAA72: ("dword",  "ResConditOffset",           "[C,A] CONDIT.HSQ resource pointer (seg:ofs)"),
    0xAA74: ("uint16", "ResConditSegment",          "[C,A] CONDIT.HSQ resource segment"),
    0xAA76: ("uint16", "ResDialogueOffset",         "[A] DIALOGUE.HSQ resource offset"),
    0xAA78: ("uint16", "ResDialogueSegment",        "[A] DIALOGUE.HSQ resource segment"),
    0xAAD6: ("uint16", "var_AAD6",                  "[C] word"),
    0xAB6A: ("uint16", "var_AB6A",                  "[C] word"),
    0xAB84: ("uint16", "var_AB84",                  "[C] word"),

    # =========================================================================
    # RESOURCE MANAGEMENT (0xCE66 - 0xCEEB)
    # =========================================================================
    0xCE66: ("byte",   "var_CE66",                  "[C] byte"),
    0xCE68: ("uint16", "AllocatorLastFreeSegment",  "[C,A] last free segment for bump allocator"),
    0xCE70: ("byte",   "var_CE70",                  "[C] byte"),
    0xCE71: ("byte",   "DisableHsq",               "[C,A] flag to disable HSQ decompression"),
    0xCE72: ("byte",   "var_CE72",                  "[C] byte"),
    0xCE73: ("byte",   "var_CE73",                  "[C] byte"),
    0xCE74: ("uint16", "var_CE74",                  "[C] word"),
    0xCE76: ("byte",   "var_CE76",                  "[C] byte"),
    0xCE77: ("byte",   "var_CE77",                  "[C] byte"),
    0xCE78: ("uint16", "ResourceIndex",             "[C,A] index into DUNE.DAT resource table"),
    0xCE7A: ("uint16", "VideoPlayRelatedIndex",     "[C,A] video/dialogue play index (ASM: 'time_passed')"),
    0xCE7B: ("uint16", "var_CE7B",                  "[C] word"),
    0xCE7C: ("uint16", "var_CE7C",                  "[C] word"),
    0xCE80: ("byte",   "var_CE80",                  "[C] byte"),
    0xCE9A: ("byte",   "KeyPStatus",               "[C,A] keyboard: P key pressed status"),
    0xCE9D: ("byte",   "KeyEnterStatus",            "[C,A] keyboard: Enter key pressed status"),
    0xCE9E: ("byte",   "KeyWStatus",               "[A] keyboard: W key pressed status"),
    0xCEBA: ("byte",   "var_CEBA",                  "[C] byte"),
    0xCEE6: ("byte",   "var_CEE6",                  "[C] byte"),
    0xCEE8: ("byte",   "KeyHit",                    "[C,A] keyboard: any key hit flag; cleared on intro skip"),
    0xCEE9: ("byte",   "var_CEE9",                  "[C] byte"),
    0xCEEA: ("byte",   "ResetKeyboardCounter",      "[C] keyboard reset counter"),
    0xCEEB: ("byte",   "LanguageSetting",           "[C,A] 0=FR, 1=EN, 2=DE; game language"),

    # =========================================================================
    # FRAMEBUFFERS / DISPLAY (0xD810 - 0xDCE8)
    # =========================================================================
    0xD810: ("uint16", "var_D810",                  "[C] word"),
    0xD816: ("uint16", "var_D816",                  "[C] word"),
    0xD820: ("uint16", "var_D820",                  "[C] word"),
    0xD824: ("uint16", "var_D824",                  "[C] word"),
    0xD826: ("uint16", "var_D826",                  "[C] word"),
    0xD828: ("uint16", "var_D828",                  "[C] word"),
    0xD82C: ("uint16", "CharacterXCoord",           "[C,X] character X position on screen"),
    0xD82E: ("uint16", "CharacterYCoord",           "[C,X] character Y position on screen"),
    0xD830: ("uint16", "var_D830",                  "[C] word"),
    0xD832: ("uint16", "var_D832",                  "[C] word"),
    0xD834: ("uint16", "RoomTransitionDest1",       "[X] 8 bytes; destination for room transition memcopy"),
    0xD836: ("uint16", "var_D836",                  "[C] word"),
    0xD838: ("uint16", "var_D838",                  "[C] word"),
    0xD83A: ("uint16", "var_D83A",                  "[C] word"),
    0xD83C: ("uint16", "RoomTransitionDest2",       "[X] 8 bytes; destination for room change memcopy"),
    0xDBB0: ("dword",  "SpriteSheetResourcePtr",    "[C,A] pointer to loaded sprite sheet resource (seg:ofs)"),
    0xDBB2: ("uint16", "SpriteSheetSegment",        "[C] sprite sheet segment (high word of ptr)"),
    0xDBB4: ("byte",   "var_DBB4",                  "[C] byte"),
    0xDBB5: ("byte",   "HnmFlagMsb",               "[C,A] HNM video flag MSB"),
    0xDBBA: ("uint16", "var_DBBA",                  "[C] word"),
    0xDBBC: ("dword",  "DnmajFuncPtr2",             "[C,A] function pointer (DNMAJ audio callback?)"),
    0xDBBE: ("uint16", "var_DBBE",                  "[C] word"),
    0xDBC8: ("uint16", "PcmDriverStatus",           "[C,X] PCM driver status; bit 0=enabled, 0x100=active"),
    0xDBCB: ("byte",   "var_DBCB",                  "[C] byte"),
    0xDBCD: ("byte",   "IsSoundPresent",            "[C] flag: sound hardware detected"),
    0xDBCE: ("uint16", "MidiFunc5ReturnBx",         "[C] MIDI driver function 5 return value"),
    0xDBD6: ("uint16", "FramebufferFront",          "[C,A] front framebuffer segment (VGA display)"),
    0xDBD8: ("uint16", "ScreenBuffer",              "[C,A] screen/text buffer segment"),
    0xDBDA: ("uint16", "FramebufferActive",         "[C,A] currently active framebuffer segment for drawing"),
    0xDBDC: ("uint16", "Framebuffer2Offset",        "[A] secondary framebuffer offset"),
    0xDBDE: ("uint16", "Framebuffer2Segment",       "[C,A] secondary framebuffer segment"),
    0xDBE0: ("uint16", "var_DBE0",                  "[C] word"),
    0xDBE2: ("uint16", "var_DBE2",                  "[C] word"),
    0xDBE4: ("uint16", "var_DBE4",                  "[C] byte+word access"),
    0xDBE5: ("byte",   "var_DBE5",                  "[C] byte"),
    0xDBE6: ("byte",   "var_DBE6",                  "[C] byte"),

    # =========================================================================
    # HNM VIDEO PLAYBACK (0xDBE7 - 0xDC6A)
    # =========================================================================
    0xDBE7: ("byte",   "HnmFinishedFlag",           "[C,A] 0xFF when HNM video finished; cleared before play"),
    0xDBE8: ("uint16", "HnmFrameCounter",           "[C,A] current HNM video frame number"),
    0xDBEA: ("uint16", "HnmCounter2",               "[C,A] secondary HNM counter"),
    0xDBEC: ("uint16", "var_DBEC",                  "[C] word"),
    0xDBEE: ("uint16", "var_DBEE",                  "[C] word"),
    0xDBF6: ("uint16", "var_DBF6",                  "[C] word"),
    0xDBF8: ("uint16", "var_DBF8",                  "[C] word"),
    0xDBFA: ("uint16", "var_DBFA",                  "[C] word"),
    0xDBFC: ("uint16", "var_DBFC",                  "[C] word"),
    0xDBFE: ("uint16", "CurrentHnmResourceFlag",    "[C,A] current HNM resource flag/identifier"),
    0xDBFF: ("byte",   "var_DBFF",                  "[C] byte"),
    0xDC00: ("uint16", "HnmVideoId",               "[C,A] HNM video identifier"),
    0xDC02: ("uint16", "HnmActiveVideoId",          "[C,A] currently playing HNM video ID"),
    0xDC04: ("dword",  "HnmFileOffset",             "[C,X,A] 32-bit file offset into HNM video file"),
    0xDC06: ("uint16", "HnmFileOffsetHi",           "[C,A] high word of HNM file offset"),
    0xDC08: ("dword",  "HnmFileRemain",             "[C,X,A] 32-bit bytes remaining in HNM file"),
    0xDC0A: ("uint16", "HnmFileRemainHi",           "[C,A] high word of HNM file remaining"),
    0xDC0C: ("dword",  "HnmFileReadBufSeg",         "[C,A] HNM file read buffer segment:offset"),
    0xDC0E: ("uint16", "var_DC0E",                  "[C] word"),
    0xDC10: ("dword",  "HnmFileReadBufOfs",         "[C,A] HNM file read buffer offset"),
    0xDC12: ("uint16", "var_DC12",                  "[C] word"),
    0xDC14: ("uint16", "VideoDecodeBufOfs",          "[C,A] video decode buffer offset"),
    0xDC16: ("uint16", "VideoDecodeBufSeg",          "[C,A] video decode buffer segment"),
    0xDC18: ("uint16", "var_DC18",                  "[C] word"),
    0xDC1A: ("uint16", "HnmReadProgress",           "[C,X] incremented by read length; HNM read progress"),
    0xDC1C: ("uint16", "HnmSdBlockOffset",          "[C,A] HNM SD (sound data) block offset"),
    0xDC1E: ("uint16", "HnmPlBlockOffset",          "[C,A] HNM PL (palette) block offset"),
    0xDC20: ("uint16", "var_DC20",                  "[C] word"),
    0xDC22: ("uint16", "VideoPlayRelatedIndex2",    "[C,X] copied from CE7A; video play state"),
    0xDC24: ("uint16", "VideoChunkTag",             "[C,A] current HNM video chunk tag identifier"),
    0xDC26: ("uint16", "PcmVocLipsyncData",         "[C,A] PCM VOC lipsync data for dialogue animation"),
    0xDC28: ("uint16", "var_DC28",                  "[C] word"),
    0xDC2A: ("byte",   "var_DC2A",                  "[C] byte"),
    0xDC2B: ("byte",   "PcmAudioActive",            "[C,X] tested for zero; PCM audio currently playing flag"),

    # =========================================================================
    # MOUSE / CURSOR (0xDC32 - 0xDC6A)
    # =========================================================================
    0xDC32: ("uint16", "FramebufferBack",           "[C,A] back framebuffer segment (for double-buffering)"),
    0xDC34: ("uint16", "var_DC34",                  "[C] byte+word access"),
    0xDC35: ("byte",   "var_DC35",                  "[C] byte"),
    0xDC36: ("uint16", "MousePosY",                 "[C,A] current mouse Y position"),
    0xDC38: ("uint16", "MousePosX",                 "[C,A] current mouse X position"),
    0xDC42: ("uint16", "MouseDrawPosY",             "[C,A] mouse cursor draw Y position"),
    0xDC44: ("uint16", "MouseDrawPosX",             "[C,A] mouse cursor draw X position"),
    0xDC46: ("byte",   "CursorHideCounter",         "[C,A] cursor hide nesting counter; 0=visible"),
    0xDC47: ("byte",   "CursorUnknown",             "[C,A] cursor state unknown"),
    0xDC48: ("uint16", "var_DC48",                  "[C] word"),
    0xDC4B: ("byte",   "var_DC4B",                  "[C] byte"),
    0xDC51: ("uint16", "var_DC51",                  "[C] word"),
    0xDC53: ("uint16", "var_DC53",                  "[C] word"),
    0xDC55: ("uint16", "var_DC55",                  "[C] word"),
    0xDC57: ("byte",   "var_DC57",                  "[C] byte"),
    0xDC58: ("uint16", "MapCursorType",             "[C,X] 0=disabled; 0x149C=orni; 0x2448=globe/results"),
    0xDC5A: ("uint16", "var_DC5A",                  "[C] word"),
    0xDC5C: ("uint16", "var_DC5C",                  "[C] word"),
    0xDC5E: ("uint16", "var_DC5E",                  "[C] word"),
    0xDC60: ("uint16", "var_DC60",                  "[C] word"),
    0xDC62: ("uint16", "var_DC62",                  "[C] word"),
    0xDC64: ("uint16", "var_DC64",                  "[C] word"),
    0xDC66: ("uint16", "var_DC66",                  "[C] word"),
    0xDC68: ("uint16", "var_DC68",                  "[C] word"),
    0xDC6A: ("uint16", "InitClearWord",             "[C,X] cleared to 0 during init"),

    # =========================================================================
    # GFX TRANSITION / PALETTE (0xDCE4 - 0xDD0F)
    # =========================================================================
    0xDCE4: ("byte",   "var_DCE4",                  "[C] byte"),
    0xDCE5: ("byte",   "var_DCE5",                  "[C] byte"),
    0xDCE6: ("byte",   "TransitionBitmask",         "[C,A,X] transition effect bitmask; 0x80=in_transition"),
    0xDCE7: ("byte",   "var_DCE7",                  "[C] byte"),
    0xDCE8: ("byte",   "var_DCE8",                  "[C] byte"),
    0xDCF1: ("byte",   "var_DCF1",                  "[C] byte"),
    0xDCF2: ("uint16", "var_DCF2",                  "[C] word"),
    0xDCF4: ("uint16", "var_DCF4",                  "[C] word"),
    0xDCF6: ("uint16", "var_DCF6",                  "[C] word"),
    0xDCF8: ("uint16", "var_DCF8",                  "[C] word"),
    0xDCFA: ("uint16", "var_DCFA",                  "[C] word"),
    0xDCFC: ("uint16", "var_DCFC",                  "[C] word"),
    0xDCFE: ("dword",  "var_DCFE",                  "[C] word+dword access"),
    0xDD00: ("uint16", "var_DD00",                  "[C] word"),
    0xDD02: ("byte",   "var_DD02",                  "[C] byte"),
    0xDD03: ("byte",   "var_DD03",                  "[C] byte"),
    0xDD0F: ("uint16", "var_DD0F",                  "[C] word"),
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
