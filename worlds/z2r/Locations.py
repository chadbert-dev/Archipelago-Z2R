import json
import pkgutil

from BaseClasses import Location

BASE_LOCATION_ID = 0x5A2100
GOAL_EVENT = "Defeated Dark Link"
GOAL_NODE = "EAST_GREAT_PALACE:room1"


class Z2RLocation(Location):
    game = "Zelda II: Z2R"


# The set of locations does not change between seeds, only the requirements do. IDs are the index in
# data/locations.json, so new locations must only ever be appended to that file.
LOCATION_NAMES: list[str] = json.loads(pkgutil.get_data(__name__, "data/locations.json"))
LOCATION_NAME_TO_ID: dict[str, int] = {name: BASE_LOCATION_ID + i for i, name in enumerate(LOCATION_NAMES)}

# Each palace boss drops a crystal. The Great Palace, Thunderbird and Dark Link need all of them.
# TODO: the Z2R app's output does not say how many crystals are required, and the count is configurable there.
# Add it to the requirements/ap_locations output and read it from the YAML instead of this constant.
CRYSTALS_REQUIRED = 6
CRYSTAL_ITEM = "Crystal"
PALACE_BOSS_NODES = [
    "WEST_PALACE1:room1",
    "WEST_PALACE2:room1",
    "WEST_PALACE3:room1",
    "MI_PALACE4:room1",
    "EAST_PALACE5:room1",
    "EAST_PALACE6:room1",
]
