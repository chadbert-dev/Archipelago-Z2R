import json
import os

from test.bases import WorldTestBase
from ..convert import build_options

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class Z2RTestBase(WorldTestBase):
    game = "Zelda II: Z2R"

    def world_setup(self, *args, **kwargs) -> None:
        with open(os.path.join(DATA_DIR, "requirements.json")) as f:
            requirements = json.load(f)
        with open(os.path.join(DATA_DIR, "ap_locations.json")) as f:
            ap_locations = json.load(f)
        self.options = {
            **build_options(requirements, ap_locations),
            "starting_items": {"Candle": 1, "Life Spell": 1, "Fairy Spell": 1, "Downstab": 1},
            "start_magic_containers": 4,
            "start_heart_containers": 4,
            "replace_fire_with_dash": False,
        }
        super().world_setup(*args, **kwargs)
