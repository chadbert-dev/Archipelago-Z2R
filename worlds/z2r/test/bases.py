import os

import yaml

from test.bases import WorldTestBase

SAMPLE_YAML = os.path.join(os.path.dirname(__file__), "data", "sample.yaml")


class Z2RTestBase(WorldTestBase):
    game = "Z2R"

    def world_setup(self, *args, **kwargs) -> None:
        # A player YAML written by the Z2R app
        with open(SAMPLE_YAML) as f:
            self.options = yaml.safe_load(f)["Z2R"]
        super().world_setup(*args, **kwargs)
