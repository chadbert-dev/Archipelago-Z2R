import json
import pkgutil

from BaseClasses import Location

BASE_LOCATION_ID = 0x5A2100
GOAL_EVENT = "Defeated Dark Link"


class Z2RLocation(Location):
    game = "Z2R"


# The set of locations does not change between seeds, only the requirements do. IDs are the index in
# data/locations.json, so new locations must only ever be appended to that file.
LOCATION_NAMES: list[str] = json.loads(pkgutil.get_data(__name__, "data/locations.json"))
LOCATION_NAME_TO_ID: dict[str, int] = {name: BASE_LOCATION_ID + i for i, name in enumerate(LOCATION_NAMES)}

# Each palace boss drops a crystal. The Great Palace (named by the great_palace option, since palaces can swap
# places) needs crystals_required of the others defeated.
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
    "EAST_GREAT_PALACE:boss",
]
