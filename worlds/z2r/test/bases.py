import os

import yaml

from test.bases import WorldTestBase

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class Z2RTestBase(WorldTestBase):
    game = "Z2R"
    # A player YAML written by the Z2R app, in test/data
    sample = "sample.yaml"

    def world_setup(self, *args, **kwargs) -> None:
        with open(os.path.join(DATA_DIR, self.sample)) as f:
            self.options = yaml.safe_load(f)["Z2R"]
        super().world_setup(*args, **kwargs)
