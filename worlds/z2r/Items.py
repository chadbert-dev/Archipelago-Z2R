from typing import NamedTuple

from BaseClasses import Item, ItemClassification

BASE_ITEM_ID = 0x5A2000


class Z2RItem(Item):
    game = "Z2R"


class ItemData(NamedTuple):
    # Matches the Collectable enum in the Z2R app, so the ID is BASE_ITEM_ID + collectable
    collectable: int
    classification: ItemClassification
    # RAM address and bit mask the client sets when the item is received, or None if it is not delivered by flag
    address: int | None = None
    mask: int = 0xFF


PROG = ItemClassification.progression
USEFUL = ItemClassification.useful
FILLER = ItemClassification.filler

# Inventory addresses are from RandomizerCore/Asm/ram.inc in the Z2R app
ITEM_TABLE: dict[str, ItemData] = {
    "Candle": ItemData(0x00, USEFUL, 0x0785),
    "Glove": ItemData(0x01, PROG, 0x0786),
    "Raft": ItemData(0x02, PROG, 0x0787),
    "Boots": ItemData(0x03, PROG, 0x0788),
    "Flute": ItemData(0x04, PROG, 0x0789),
    "Cross": ItemData(0x05, USEFUL, 0x078A),
    "Hammer": ItemData(0x06, PROG, 0x078B),
    "Magic Key": ItemData(0x07, PROG, 0x078C),
    "Magic Container": ItemData(0x0E, PROG),  # counted, see CONTAINER_ITEMS
    "Heart Container": ItemData(0x0F, USEFUL),  # counted, see CONTAINER_ITEMS
    "Child": ItemData(0x13, PROG, 0x079C, 0x20),
    "Trophy": ItemData(0x14, PROG, 0x0798, 0x10),
    "Medicine": ItemData(0x15, PROG, 0x079A, 0x40),
    "Upstab": ItemData(0x17, PROG, 0x0796, 0x04),
    "Downstab": ItemData(0x18, PROG, 0x0796, 0x10),
    "Bagu's Note": ItemData(0x19, PROG, 0x079A, 0x08),
    "Mirror": ItemData(0x1A, PROG, 0x0799, 0x01),
    "Water": ItemData(0x1B, PROG, 0x079B, 0x01),
    "Shield Spell": ItemData(0x1C, USEFUL, 0x077B),
    "Jump Spell": ItemData(0x1D, PROG, 0x077C),
    "Life Spell": ItemData(0x1E, USEFUL, 0x077D),
    "Fairy Spell": ItemData(0x1F, PROG, 0x077E),
    "Fire Spell": ItemData(0x20, USEFUL, 0x077F),
    "Reflect Spell": ItemData(0x21, PROG, 0x0780),
    "Spell Spell": ItemData(0x22, PROG, 0x0781),
    "Thunder Spell": ItemData(0x23, PROG, 0x0782),
    # The app replaces Fire with Dash when "ReplaceFireWithDash" is set, so Dash uses the Fire spell flag
    "Dash Spell": ItemData(0x24, PROG, 0x077F),
    # Filler is not delivered yet
    "Blue Magic Jar": ItemData(0x10, FILLER),
    "Red Magic Jar": ItemData(0x11, FILLER),
    "1-Up": ItemData(0x12, FILLER),
    "Small P-Bag": ItemData(0x0A, FILLER),
    "Large P-Bag": ItemData(0x0C, FILLER),
    "Small Key": ItemData(0x08, FILLER),
}

ITEM_NAME_TO_ID: dict[str, int] = {name: BASE_ITEM_ID + data.collectable for name, data in ITEM_TABLE.items()}

# Counted items: name -> (RAM address of the count, maximum)
CONTAINER_ITEMS: dict[str, tuple[int, int]] = {
    "Magic Container": (0x0783, 8),
    "Heart Container": (0x0784, 8),
}

FILLER_ITEMS = ["Blue Magic Jar", "Red Magic Jar", "1-Up", "Small P-Bag", "Large P-Bag", "Small Key"]

# Order used to decide which items to keep when there are fewer locations than items
POOL_PRIORITY = [name for name, data in ITEM_TABLE.items() if data.classification == PROG] + \
                [name for name, data in ITEM_TABLE.items() if data.classification == USEFUL]

# Requirement tokens in the Z2R requirements file that are single items
REQUIREMENT_ITEMS: dict[str, str] = {
    "JUMP": "Jump Spell",
    "FAIRY": "Fairy Spell",
    "UPSTAB": "Upstab",
    "DOWNSTAB": "Downstab",
    "KEY": "Magic Key",
    "DASH": "Dash Spell",
    "GLOVE": "Glove",
    "REFLECT": "Reflect Spell",
    "THUNDER": "Thunder Spell",
    "SPELL": "Spell Spell",
    "TROPHY": "Trophy",
    "MEDICINE": "Medicine",
    "CHILD": "Child",
    "MIRROR": "Mirror",
    "WATER": "Water",
    "BOOTS": "Boots",
    "FLUTE": "Flute",
    "HAMMER": "Hammer",
    "BAGU_LETTER": "Bagu's Note",
    "RAFT": "Raft",
}

# Tokens meaning "at least N magic containers in total"
CONTAINER_REQUIREMENTS: dict[str, int] = {
    "ONE_CONTAINER": 1,
    "TWO_CONTAINERS": 2,
    "THREE_CONTAINERS": 3,
    "FOUR_CONTAINERS": 4,
    "FIVE_CONTAINERS": 5,
    "SIX_CONTAINERS": 6,
    "SEVEN_CONTAINERS": 7,
    "EIGHT_CONTAINERS": 8,
}

# The Z2R app names this item "Bagus Note"
ITEM_ALIASES = {"Bagus Note": "Bagu's Note"}

# Items the Z2R app leaves out of the pool when the matching include_*_in_shuffle option is off
SPELL_ITEMS = ["Shield Spell", "Jump Spell", "Life Spell", "Fairy Spell", "Fire Spell", "Reflect Spell",
               "Spell Spell", "Thunder Spell", "Dash Spell"]
SWORD_TECH_ITEMS = ["Upstab", "Downstab"]
QUEST_ITEMS = ["Water", "Bagu's Note", "Mirror"]
