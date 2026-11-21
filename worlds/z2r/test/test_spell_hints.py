import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from .. import Client
from ..spell_hints import HINT_LOCATION_NAMES, SPELL_HINT_ITEMS, spell_hint_text, unplaced_spell_hint_text


class SpellHintTextTest(unittest.TestCase):
    def test_names_the_owner_and_location(self) -> None:
        self.assertEqual(spell_hint_text("Trophy", "Gob-DWR", "DM_HAMMER_CAVE", True),
                         "TROPHY AT$GOB-DWR$DM HAMMER$CAVE")

    def test_own_item_says_your_and_no_player_line(self) -> None:
        self.assertEqual(spell_hint_text("Trophy", "Gob-Z2R", "WEST_CAVE_TROPHY", True, own=True),
                         "YOUR TROPHY$AT$TROPHY CAVE")

    def test_own_item_at_a_long_place(self) -> None:
        self.assertEqual(spell_hint_text("Medicine", "Gob-Z2R", "EAST_CAVE_PBAG1", True, own=True),
                         "YOUR$MEDICINE AT$SUNKEN PBAG$CAVE")

    def test_owner_name_is_cut_to_eleven(self) -> None:
        text = spell_hint_text("Water", "Gob Is Very Long", "WEST_GRASS", True)
        self.assertEqual(text.split("$")[1], "GOB IS VERY")

    def test_other_game_location_is_generic(self) -> None:
        self.assertEqual(spell_hint_text("Mirror", "Tetra", "Tantegel Treasury Chest 1", False),
                         "MIRROR AT$TETRA$ANOTHER$GAME")

    def test_dwr_location_uses_its_short_name(self) -> None:
        self.assertEqual(spell_hint_text("Medicine", "Gob-DWR", "Garin's Grave Chest 3", False, game="DWR"),
                         "MEDICINE AT$GOB-DWR$GRAVE 3")

    def test_zora_names(self) -> None:
        self.assertEqual(spell_hint_text("Medicine", "Gob-ZORA", "Shop 2 Middle", False, game="ZORA"),
                         "MEDICINE AT$GOB-ZORA$SHOP 2 MID")
        self.assertEqual(spell_hint_text("Medicine", "Gob-ZORA", "Level 4 Room 0A Floor", False, game="ZORA"),
                         "MEDICINE AT$GOB-ZORA$LEVEL 4")

    def test_every_other_game_name_fits_two_lines(self) -> None:
        from ..spell_hints import OTHER_GAME_LOCATION_NAMES
        for game, names in OTHER_GAME_LOCATION_NAMES.items():
            for location in names:
                with self.subTest(game=game, location=location):
                    self.assertIsNotNone(spell_hint_text("Upstab", "Gob-DWR", location, False, game=game))

    def test_location_too_long_falls_back_instead_of_none(self) -> None:
        text = spell_hint_text("Water", "Tetra", "Some Extremely Long Location Name Here", False, game="DWR")
        self.assertEqual(text, "WATER AT$TETRA$ANOTHER$GAME")

    def test_unplaced_items_still_get_text(self) -> None:
        for item in SPELL_HINT_ITEMS:
            for precollected in (True, False):
                text = unplaced_spell_hint_text(item, precollected)
                self.assertLessEqual(len(text.split("$")), 4)
                self.assertTrue(all(len(line) <= 11 for line in text.split("$")), text)
                self.assertIsNotNone(Client.spell_hint_bytes(text, item))

    def test_every_location_name_fits_two_lines(self) -> None:
        for location in HINT_LOCATION_NAMES:
            with self.subTest(location=location):
                self.assertIsNotNone(spell_hint_text("Upstab", "Gob-Z2R", location, True))

    def test_bytes_are_49_and_end_with_the_item_number(self) -> None:
        for number, item in enumerate(SPELL_HINT_ITEMS):
            with self.subTest(item=item):
                data = Client.spell_hint_bytes("TROPHY AT$GOB$ANOTHER$GAME", item)
                self.assertEqual(len(data), Client.SPELL_HINT_SIZE)
                self.assertEqual(data[-1], 0xA0 + number)

    def test_placeholder_is_recognised(self) -> None:
        self.assertEqual(Client.spell_hint_bytes("AP HINT", "Downstab")[-1], 0xA0 + SPELL_HINT_ITEMS.index("Downstab"))


class SpellHintCheckTest(unittest.TestCase):
    ADDRESS = 0xA600

    def make_ctx(self, texts: dict[str, str]) -> SimpleNamespace:
        return SimpleNamespace(bizhawk_ctx=None, slot_data={
            "spell_hint_slots": {"Trophy": 13}, "spell_hints": texts})

    def run_check(self, ctx, memory: dict[int, bytes], client: Client.Z2RClient) -> None:
        async def read(_ctx, reads):
            return [memory.get(address, b"") for address, _size, _domain in reads]

        async def write(_ctx, writes):
            for address, data, _domain in writes:
                memory[address] = data

        async def addresses(_ctx, indexes):
            return [self.ADDRESS for _ in indexes]

        with mock.patch.object(Client.bizhawk, "read", read), mock.patch.object(Client.bizhawk, "write", write), mock.patch.object(Client.bizhawk, "guarded_write", lambda _c, w, _g: write(_c, w)), \
                mock.patch.object(Client.Z2RClient, "text_addresses", staticmethod(addresses)):
            asyncio.run(client.spell_hint_check(ctx))

    def test_placeholder_is_written_with_the_text(self) -> None:
        memory = {self.ADDRESS: Client.spell_hint_bytes("AP HINT", "Trophy")}
        self.run_check(self.make_ctx({"Trophy": "TROPHY AT$GOB$ANOTHER$GAME"}), memory, Client.Z2RClient())
        self.assertEqual(memory[self.ADDRESS], Client.spell_hint_bytes("TROPHY AT$GOB$ANOTHER$GAME", "Trophy"))

    def test_other_text_is_left_alone(self) -> None:
        # text the app didn't leave as a placeholder: no marker byte at the end
        other = Client.encode_text("SOMETHING ELSE").ljust(Client.SPELL_HINT_SIZE, b"\x00")
        memory = {self.ADDRESS: other}
        self.run_check(self.make_ctx({"Trophy": "TROPHY AT$GOB$ANOTHER$GAME"}), memory, Client.Z2RClient())
        self.assertEqual(memory[self.ADDRESS], other)

    def test_restarted_client_updates_its_own_hint(self) -> None:
        # a client wrote this hint, then restarted (forgetting what it wrote) while the game kept the text
        earlier = Client.spell_hint_bytes("SOMETHING ELSE", "Trophy")
        memory = {self.ADDRESS: earlier}
        self.run_check(self.make_ctx({"Trophy": "TROPHY AT$GOB$ANOTHER$GAME"}), memory, Client.Z2RClient())
        self.assertEqual(memory[self.ADDRESS], Client.spell_hint_bytes("TROPHY AT$GOB$ANOTHER$GAME", "Trophy"))

    def test_item_without_text_is_not_touched(self) -> None:
        placeholder = Client.spell_hint_bytes("AP HINT", "Trophy")
        memory = {self.ADDRESS: placeholder}
        client = Client.Z2RClient()
        self.run_check(self.make_ctx({}), memory, client)
        self.assertEqual(memory[self.ADDRESS], placeholder)
        self.assertEqual(client.next_spell_check, float("inf"))
