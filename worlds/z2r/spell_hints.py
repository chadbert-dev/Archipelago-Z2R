"""Spell item hints in Archipelago mode: where a spell item of this slot is, for the Z2R app's hint NPCs.

The Z2R app reserves a placeholder for each of these items (CustomTexts.ArchipelagoSpellHintPlaceholder), in the
order below, and the YAML lists the text index of each as spell_hint_slots. The client writes the text from
slot data (spell_hints) over the placeholder.
"""
import re
import textwrap

# The order of the Z2R app's ARCHIPELAGO_SPELL_HINT_ITEMS: each placeholder's last byte is 0xA0 + its position
SPELL_HINT_ITEMS = ("Trophy", "Medicine", "Child", "Mirror", "Water", "Downstab", "Upstab")

# The name of each location in Z2R's own world, as the hint says it (two lines of 11 characters). Locations of
# other games are named "ANOTHER GAME".
HINT_LOCATION_NAMES: dict[str, str] = {
    "WEST_CAVE_MAGIC_CONTAINER": "MC CAVE",
    "WEST_CAVE_HEART_CONTAINER": "HC CAVE",
    "WEST_CAVE_MEDICINE": "MEDICINE CAVE",
    "WEST_CAVE_PBAG": "PILLAR PBAG CAVE",
    "WEST_CAVE_TROPHY": "TROPHY CAVE",
    "WEST_GRASS": "GRASS TILE",
    "WEST_TOWN_RAURU:wizard": "RAURU",
    "WEST_TOWN_RUTO:wizard": "RUTO",
    "WEST_TOWN_SARIA_NORTH:table": "SARIA TABLE",
    "WEST_TOWN_SARIA_NORTH:wizard": "SARIA",
    "WEST_TOWN_MIDO:wizard": "MIDO",
    "WEST_TOWN_MIDO:downstab_man": "DOWNSTAB GUY",
    "BAGU": "BAGU",
    "DM_HAMMER_CAVE": "DM HAMMER CAVE",
    "DM_SPEC_ROCK": "DM SPEC ROCK",
    "EAST_WATER": "WATER TILE",
    "EAST_DESERT": "DESERT TILE",
    "EAST_CAVE_PBAG1": "SUNKEN PBAG CAVE",
    "EAST_CAVE_PBAG2": "RISEN PBAG CAVE",
    "EAST_TOWN_NABOORU:fountain": "NABOORU FOUNTAIN",
    "EAST_TOWN_NABOORU:wizard": "NABOORU",
    "EAST_TOWN_DARUNIA:wizard": "DARUNIA",
    "EAST_TOWN_DARUNIA:upstab_man": "UPSTAB GUY",
    "EAST_TOWN_NEW_KASUTO:ganon_granny": "NK GRANNY",
    "EAST_TOWN_NEW_KASUTO:wizard": "NEW KASUTO",
    "EAST_TOWN_NEW_KASUTO:spell_tower": "NK TOWER",
    "EAST_TOWN_OLD_KASUTO:wizard": "OLD KASUTO",
    "MI_CHILD_DROP": "MAZE LONG DROP",
    "MI_MAGIC_CONTAINER_DROP": "MAZE SHORT DROP",
    **{f"PALACE{palace}:{part}": f"PALACE{palace} {part.upper()}"
       for palace in range(1, 7) for part in ("item1", "item2", "item3", "crystal")},
}

OTHER_GAME_LOCATION = "ANOTHER GAME"

# Short names of other games' locations, by game, for hints about an item in another world. A location not listed
# here is named OTHER_GAME_LOCATION.
OTHER_GAME_LOCATION_NAMES: dict[str, dict[str, str]] = {
    "ZORA": {
        "Armos": "ARMOS",
        "Coast": "COAST",
        "White Sword Cave": "W-SWORD CAVE",
        "Magical Sword Cave": "M-SWORD CAVE",
        "Letter Cave": "LETTER CAVE",
        "Wood Sword Cave": "WOOD SWORD",
        "Potion Shop Left": "POTION L",
        "Potion Shop Middle": "POTION MID",
        "Potion Shop Right": "POTION R",
        **{f"Shop {s} {w}": f"SHOP {s} {'MID' if w == 'Middle' else w[0]}"
           for s in range(1, 5) for w in ("Left", "Middle", "Right")},
    },
    "DWR": {
        **{f"Tantegel Treasury Chest {n}": f"TANT {n}" for n in range(1, 5)},
        "Tantegel Basement Chest": "TANT BASEMENT",
        **{f"Throne Room Chest {n}": f"THRONE {n}" for n in range(1, 4)},
        "Rimuldar Chest": "RIMULDAR",
        **{f"Garinham Chest {n}": f"GARINHAM {n}" for n in range(1, 4)},
        **{f"Charlock Throne Room Chest {n}": f"CHARLOCK {n}" for n in range(1, 7)},
        "Charlock Cave Chest": "CHAR BAD SPOT",
        "Staff of Rain Shrine Chest": "STAFF CAVE",
        **{f"Garin's Grave Chest {n}": f"GRAVE {n}" for n in range(1, 6)},
        **{f"Mountain Cave Chest {n}": f"MOUNTAIN {n}" for n in range(1, 6)},
        "Erdrick's Cave Chest": "ERD/TABLET CAVE",
        "Overworld Search Spot": "COORDS",
        "Kol Search Spot": "KOL",
        "Hauksness Search Spot": "HAUKSNESS",
        "Rescue Gwaelin": "GWAELIN",
    },
}
OTHER_PLAYER = "ANOTHER PLAYER"
NAME_LENGTH = 11
ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?-_")


def _clean(name: str) -> str:
    """A name as the game can show it: upper case, the characters the font has, no extra spaces."""
    text = "".join(c if c in ALLOWED else " " for c in name.upper())
    return " ".join(text.split())


def zora_level_name(location: str) -> str | None:
    """ZORA's rooms and cellars are named "Level N Room XX Floor" and so on; each level shares one short name."""
    match = re.match(r"Level (\d) ", location)
    return f"LEVEL {match.group(1)}" if match else None


def spell_hint_text(item: str, owner: str, location: str, same_game: bool, own: bool = False,
                    game: str = "") -> str:
    """The hint for a spell item of this slot that sits in `location`. Another player's item: "<ITEM> AT", the owner's
    name (cut to 11 characters), then the location. This slot's own item: "YOUR <ITEM> AT" then the location. The
    location is in up to two lines; one that won't fit becomes ANOTHER GAME (or SOMEWHERE in this world), so the
    NPC never keeps the AP HINT placeholder."""
    where = (HINT_LOCATION_NAMES.get(location, OTHER_GAME_LOCATION) if same_game
             else (zora_level_name(location) if game == "ZORA" else None)
             or OTHER_GAME_LOCATION_NAMES.get(game, {}).get(location, OTHER_GAME_LOCATION))
    lines = textwrap.wrap(where, NAME_LENGTH, break_long_words=False)
    if len(lines) > 2 or any(len(line) > NAME_LENGTH for line in lines):
        lines = textwrap.wrap("SOMEWHERE" if same_game else OTHER_GAME_LOCATION, NAME_LENGTH)
    if own:
        head = textwrap.wrap(f"YOUR {item.upper()} AT", NAME_LENGTH, break_long_words=False)
        return "$".join([*head[:2], *lines])
    name = _clean(owner)[:NAME_LENGTH].strip() or OTHER_PLAYER
    return "$".join([f"{item.upper()} AT", name, *lines])


def unplaced_spell_hint_text(item: str, precollected: bool) -> str:
    """The hint for a spell item that sits in no location: one the player starts with, or one not in the game."""
    return f"YOU START$WITH YOUR${item.upper()}" if precollected else f"NO {item.upper()}$IN THIS$GAME"
