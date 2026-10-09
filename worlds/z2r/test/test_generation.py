from ..Locations import GOAL_EVENT, LOCATION_NAME_TO_ID
from .bases import Z2RTestBase


class TestGeneration(Z2RTestBase):
    def test_all_locations_created(self) -> None:
        names = {location.name for location in self.multiworld.get_locations(self.player)}
        self.assertEqual(names, set(self.options["locations"]) | {GOAL_EVENT} | {f"Defeat Palace Boss {i}" for i in range(1, 7)})
        self.assertTrue(set(self.options["locations"]) <= set(LOCATION_NAME_TO_ID))

    def test_pool_fills_locations(self) -> None:
        self.assertEqual(len(self.multiworld.itempool), len(self.options["locations"]))

    def test_dash_replaced_by_fairy(self) -> None:
        names = {item.name for item in self.multiworld.itempool}
        self.assertNotIn("Dash Spell", names)
        self.assertIn("Fire Spell", names)

    def test_beatable(self) -> None:
        self.assertBeatable(False)
        self.collect_all_but([])
        self.assertBeatable(True)
