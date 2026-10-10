import json
import pkgutil
import re

from BaseClasses import Location

BASE_LOCATION_ID = 0x5A2100
GOAL_EVENT = "Defeated Dark Link"
GOAL_NODE = "EAST_GREAT_PALACE:boss"


class Z2RLocation(Location):
    game = "Z2R"


# The set of locations does not change between seeds, only the requirements do. IDs are the index in
# data/locations.json, so new locations must only ever be appended to that file.
LOCATION_NAMES: list[str] = json.loads(pkgutil.get_data(__name__, "data/locations.json"))
LOCATION_NAME_TO_ID: dict[str, int] = {name: BASE_LOCATION_ID + i for i, name in enumerate(LOCATION_NAMES)}

# Each palace boss drops a crystal. The Great Palace, Thunderbird and Dark Link need crystals_required of them.
# Bump this when the layout of the YAML written by the Z2R app changes.
FORMAT_VERSION = 1
CRYSTAL_ITEM = "Crystal"
PALACE_BOSS_NODES = [
    "WEST_PALACE1:boss",
    "WEST_PALACE2:boss",
    "WEST_PALACE3:boss",
    "MI_PALACE4:boss",
    "EAST_PALACE5:boss",
    "EAST_PALACE6:boss",
]

# The Z2R app names a palace room by its index in the palace, which differs from seed to seed
# (e.g. WEST_PALACE1:room2 in one seed and WEST_PALACE1:room8 in another).
PALACE_ROOM = re.compile(r"^(?P<palace>\w+PALACE\d*):room\d+$")


def normalize_nodes(locations: dict, rules: dict, fixed_items: dict) -> tuple[dict, dict]:
    """Give palace rooms stable names: the room holding an item is "<palace>:item_room" and the palace's other
    room with a rule is its boss, "<palace>:boss"."""
    renames: dict[str, str] = {}
    for name in locations:
        if match := PALACE_ROOM.match(name):
            renames[name] = f"{match['palace']}:item_room"
    for name in rules:
        if name not in renames and name not in fixed_items and (match := PALACE_ROOM.match(name)):
            renames[name] = f"{match['palace']}:boss"
    new_names = list(renames.values())
    if len(set(new_names)) != len(new_names):
        raise Exception("Z2R has more than one item room or boss in a palace, which this version of the world "
                        f"can't tell apart: {', '.join(sorted(renames))}")
    return ({renames.get(name, name): value for name, value in locations.items()},
            {renames.get(name, name): value for name, value in rules.items()})
