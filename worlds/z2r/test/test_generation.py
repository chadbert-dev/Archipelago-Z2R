from ..Locations import GOAL_EVENT, LOCATION_NAME_TO_ID
from .bases import Z2RTestBase


class TestGeneration(Z2RTestBase):
    def test_all_locations_created(self) -> None:
        names = {location.name for location in self.multiworld.get_locations(self.player)}
        locations = set(self.world.z2r_locations)
        events = {GOAL_EVENT, *self.options.get("fixed_items", {}), *(f"Defeat Palace Boss {i}" for i in range(1, 7))}
        self.assertEqual(names, locations | events)
        self.assertTrue(locations <= set(LOCATION_NAME_TO_ID))

    def test_pool_fills_locations(self) -> None:
        self.assertEqual(len(self.multiworld.itempool), len(self.options["locations"]))

    def test_palace_rooms_are_renamed(self) -> None:
        self.assertFalse([name for name in self.world.z2r_locations if ":room" in name])

    def test_dash_replaced_by_fairy(self) -> None:
        names = {item.name for item in self.multiworld.itempool}
        self.assertNotIn("Dash Spell", names)
        self.assertIn("Fire Spell", names)

    def test_beatable(self) -> None:
        self.assertBeatable(False)
        self.collect_all_but([])
        self.assertBeatable(True)


class TestOtherSeed(TestGeneration):
    """A seed whose locations differ from the first sample's, to catch locations missing from the static table."""
    sample = "sample2.yaml"


class TestNothingShuffled(TestGeneration):
    """Spells, sword techniques and quest items are all left out of the shuffle."""
    sample = "sample3.yaml"

    def test_left_out_items_are_not_in_the_pool(self) -> None:
        names = {item.name for item in self.multiworld.itempool}
        self.assertFalse(names & {"Jump Spell", "Fairy Spell", "Upstab", "Downstab", "Water", "Mirror", "Bagu's Note"})

    def test_dash_replaced_by_fairy(self) -> None:
        self.assertNotIn("Dash Spell", {item.name for item in self.multiworld.itempool})
