import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from .. import Client, item_sprites
from ..Items import ITEM_NAME_TO_ID
from ..Locations import LOCATION_NAME_TO_ID

LOGO = item_sprites.AP_LOGO
REGULAR_LOGO = item_sprites.solid(LOGO, item_sprites.REGULAR_INDEX)
PROGRESSION_LOGO = item_sprites.solid(LOGO, item_sprites.PROGRESSION_INDEX)
CANDLE = bytes(range(32))
HEART_HALF = bytes([0xF0] * 8 + [0x00] * 8 + [0x0F] * 8 + [0x00] * 8)  # top: left 4 pixels; bottom: right 4
PALETTE_BYTE = 0x1F631  # $F60B + $26 in bank 7 (PRG 0x1C000)


class FakeEmulator:
    """CHR with the AP logo in banks 0-12 at 0xA80 (bank 13-15 hold something else) and RAM for one room."""

    def __init__(self, ram: dict[int, int], chr_banks: int = 16, palette_table: bool = True,
                 wide: bool = False, fixed: bool = False) -> None:
        self.chr = bytearray(chr_banks * item_sprites.BANK_SIZE)
        for bank in range(13):
            at = bank * item_sprites.BANK_SIZE + item_sprites.AP_TILE_OFFSET
            self.chr[at:at + 32] = item_sprites.ONE_UP_TILES if fixed else LOGO
        if fixed:  # the newest Z2R build: the logo's left half is in its own tile, the 1-up's tiles are the 1-up's
            wide = True
            at = item_sprites.FIXED_LEFT_ADDRESS
            self.chr[at:at + 32] = LOGO
        if wide:  # a ROM from a Z2R build with the 16 pixel AP item
            self.chr[item_sprites.RIGHT_TILE_ADDRESS:item_sprites.RIGHT_TILE_ADDRESS + 32] = item_sprites.AP_LOGO_RIGHT
        self.chr[0x88C0:0x88E0] = CANDLE
        self.chr[0x1800:0x1820] = HEART_HALF
        # bank 7's "lda $F60B,x" and the AP item's palette byte, as in the seed tested in FCEUX
        self.prg = bytearray(0x40000)
        if palette_table:
            self.prg[item_sprites.PALETTE_LOAD:item_sprites.PALETTE_LOAD + 3] = bytes([0xBD, 0x0B, 0xF6])
            self.prg[PALETTE_BYTE] = item_sprites.AP_PALETTE
        self.ram = ram
        self.write_calls = 0

    async def get_memory_size(self, _ctx, _domain):
        return len(self.chr)

    def domain(self, name: str) -> bytearray:
        return {item_sprites.CHR_DOMAIN: self.chr, item_sprites.PRG_DOMAIN: self.prg}[name]

    async def read(self, _ctx, reads):
        out = []
        for address, size, domain in reads:
            if domain in (item_sprites.CHR_DOMAIN, item_sprites.PRG_DOMAIN):
                out.append(bytes(self.domain(domain)[address:address + size]))
            else:
                out.append(bytes(self.ram.get(address + i, 0) for i in range(size)))
        return out

    async def guarded_read(self, ctx, reads, _guards):
        return await self.read(ctx, reads)

    async def guarded_write(self, _ctx, writes, _guards):
        self.write_calls += 1
        for address, data, domain in writes:
            self.domain(domain)[address:address + len(data)] = data
        return True

    def ap_tiles(self, bank: int) -> bytes:
        at = bank * item_sprites.BANK_SIZE + item_sprites.AP_TILE_OFFSET
        return bytes(self.chr[at:at + 32])

    def right_tiles(self) -> bytes:
        return bytes(self.chr[item_sprites.RIGHT_TILE_ADDRESS:item_sprites.RIGHT_TILE_ADDRESS + 32])


# PALACE1:item1 in the seed tested in FCEUX: palace table 0x680, map 2, page 0
LOCATIONS = {
    "PALACE1:item1": {"address": 0x681, "mask": 0x80, "collected": 0},
    "WEST_CAVE_HEART_CONTAINER": {"address": 0x608, "mask": 0x04, "collected": 0},  # map 17, page 1
    "WEST_TOWN_RAURU:wizard": {"address": 0x77A, "mask": 0x08, "collected": 1},
}
PALACE_ROOM = {item_sprites.WORLD_NUMBER: 3, item_sprites.REGION_NUMBER: 0, item_sprites.MAP_NUMBER: 2}
CAVE_ROOM = {item_sprites.WORLD_NUMBER: 0, item_sprites.REGION_NUMBER: 0, item_sprites.MAP_NUMBER: 17}


def make_ctx(placements: dict[str, tuple[str, int]], slot: int = 1, flags: int = 0b010):
    """placements: location -> (item name, player). Every item has `flags` (default useful: the orange logo)."""
    names = {ITEM_NAME_TO_ID[item]: item for item, _player in placements.values()}
    return SimpleNamespace(
        bizhawk_ctx=None, slot=slot, slot_data={"locations": LOCATIONS},
        locations_info={LOCATION_NAME_TO_ID[location]: SimpleNamespace(item=ITEM_NAME_TO_ID[item], player=player, flags=flags)
                        for location, (item, player) in placements.items()},
        item_names=SimpleNamespace(lookup_in_game=lambda item, game: names[item]))


def run(client, ctx, emulator, mode=Client.HUD_MODE):
    with mock.patch.multiple(Client.bizhawk, read=emulator.read, guarded_read=emulator.guarded_read,
                             guarded_write=emulator.guarded_write, get_memory_size=emulator.get_memory_size):
        asyncio.run(client.item_sprite_check(ctx, mode))


class TestRoomLocations(unittest.TestCase):
    def test_palace_room(self) -> None:
        self.assertEqual(item_sprites.room_locations(LOCATIONS, 3, 0, 2, 0), ["PALACE1:item1"])

    def test_cave_room_uses_the_regions_table(self) -> None:
        self.assertEqual(item_sprites.room_locations(LOCATIONS, 0, 0, 17, 1), ["WEST_CAVE_HEART_CONTAINER"])
        # the same map number in the east caves is another room
        self.assertEqual(item_sprites.room_locations(LOCATIONS, 0, 2, 17, 1), [])

    def test_other_room_and_great_palace_have_none(self) -> None:
        self.assertEqual(item_sprites.room_locations(LOCATIONS, 3, 0, 4, 0), [])
        self.assertEqual(item_sprites.room_locations(LOCATIONS, 5, 0, 2, 0), [])

    def test_nearest_page_first(self) -> None:
        both = {"A": {"address": 0x681, "mask": 0x80, "collected": 0},
                "B": {"address": 0x681, "mask": 0x10, "collected": 0}}  # pages 0 and 3 of map 2
        self.assertEqual(item_sprites.room_locations(both, 3, 0, 2, 3), ["B", "A"])
        self.assertEqual(item_sprites.room_locations(both, 3, 0, 2, 0), ["A", "B"])


class TestItemSprite(unittest.TestCase):
    def test_narrow_item_is_copied(self) -> None:
        self.assertEqual(item_sprites.item_sprite("Candle", {0x88C0: CANDLE}), CANDLE)

    def test_wide_item_is_squeezed(self) -> None:
        # left half 4 pixels on the left of the top tile; mirrored, the right half is the same on the right: the
        # 16 pixel row "1111000000001111" squeezed by pairs is "11000011"
        sprite = item_sprites.item_sprite("Heart Container", {0x1800: HEART_HALF})
        rows = item_sprites.decode(sprite)
        self.assertEqual(rows[0], [1, 1, 0, 0, 0, 0, 1, 1])
        # bottom tile: right 4 pixels of the left half, mirrored next to them: "0000111111110000" -> "00111100"
        self.assertEqual(rows[8], [0, 0, 1, 1, 1, 1, 0, 0])

    def test_mirrored_item_stays_symmetric(self) -> None:
        # an outline pixel next to a fill pixel in the left half: squeezing by pairs from the left kept the outline
        # only on the left side, so the magic container came out lopsided
        left = [[3, 1, 1, 1, 1, 1, 1, 1]] + [[0] * 8] * 15
        sprite = item_sprites.item_sprite("Magic Container", {0x1820: item_sprites.encode(left)})
        for row in item_sprites.decode(sprite):
            self.assertEqual(row, row[::-1])
        self.assertEqual(item_sprites.decode(sprite)[0], [3, 1, 1, 1, 1, 1, 1, 3])

    def test_decode_encode_round_trip(self) -> None:
        self.assertEqual(item_sprites.encode(item_sprites.decode(LOGO)), LOGO)

    def test_unknown_item_has_none(self) -> None:
        self.assertIsNone(item_sprites.item_sprite("Crystal", {}))
        self.assertIsNone(item_sprites.wide_item_sprite("Crystal", {}))

    def test_wide_sprite_keeps_both_halves(self) -> None:
        # a mirrored item: the game flips the right sprite, so its stored tiles equal the left half
        sprite = item_sprites.wide_item_sprite("Heart Container", {0x1800: HEART_HALF})
        self.assertEqual(sprite, HEART_HALF + HEART_HALF)

    def test_wide_sprite_right_half_is_stored_mirrored(self) -> None:
        # Jump: left tile, then a different, unflipped right tile; stored mirrored so the game's flip shows it as is
        right = item_sprites.encode([[1, 2, 3, 0, 0, 0, 0, 0]] * 16)
        sprite = item_sprites.wide_item_sprite("Jump Spell", {0x1A140: CANDLE, 0x1A120: right})
        self.assertEqual(sprite[:32], CANDLE)
        self.assertEqual(item_sprites.decode(sprite[32:])[0], [0, 0, 0, 0, 0, 3, 2, 1])

    def test_wide_sprite_of_narrow_item_has_blank_right(self) -> None:
        self.assertEqual(item_sprites.wide_item_sprite("Candle", {0x88C0: CANDLE}), CANDLE + item_sprites.BLANK)

    def test_logo_halves_are_the_apps(self) -> None:
        # ArchipelagoLogo.Logo and LogoRight in the Z2R app
        self.assertEqual(item_sprites.AP_LOGO_RIGHT.hex(),
                         "00020201000100380307037d7dffc6387cdcfb77670707037cfcfb7777070703")


class TestItemSpriteCheck(unittest.TestCase):
    def test_own_item_drawn_in_every_logo_bank_only(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM)
        client = Client.Z2RClient()
        run(client, make_ctx({"PALACE1:item1": ("Candle", 1)}), emulator)
        for bank in range(13):
            self.assertEqual(emulator.ap_tiles(bank), CANDLE)
        self.assertEqual(emulator.ap_tiles(13), bytes(32))

    def test_other_players_item_keeps_the_logo(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM)
        client = Client.Z2RClient()
        ctx = make_ctx({"PALACE1:item1": ("Candle", 2)})
        run(client, ctx, emulator)
        self.assertEqual(emulator.ap_tiles(0), REGULAR_LOGO)
        emulator.write_calls = 0
        run(client, ctx, emulator)
        self.assertEqual(emulator.write_calls, 0)

    def test_logo_comes_back_in_another_room(self) -> None:
        emulator = FakeEmulator(dict(PALACE_ROOM))
        client = Client.Z2RClient()
        ctx = make_ctx({"PALACE1:item1": ("Candle", 1), "WEST_CAVE_HEART_CONTAINER": ("Hammer", 2)})
        run(client, ctx, emulator)
        self.assertEqual(emulator.ap_tiles(5), CANDLE)
        emulator.ram.update(CAVE_ROOM)
        run(client, ctx, emulator)
        self.assertEqual(emulator.ap_tiles(5), REGULAR_LOGO)

    def test_no_writes_while_nothing_changes(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM)
        client = Client.Z2RClient()
        ctx = make_ctx({"PALACE1:item1": ("Candle", 1)})
        run(client, ctx, emulator)
        run(client, ctx, emulator)
        self.assertEqual(emulator.write_calls, 1)

    def test_unscouted_room_keeps_the_logo(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM)
        run(Client.Z2RClient(), make_ctx({}), emulator)
        self.assertEqual(emulator.ap_tiles(0), LOGO)

    def test_overworld_does_nothing(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM)
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Candle", 1)}), emulator, mode=0x05)
        self.assertEqual(emulator.ap_tiles(0), LOGO)

    def test_restarted_client_restores_the_logo(self) -> None:
        # an earlier run left the candle drawn; in a room with another player's item the logo goes back
        emulator = FakeEmulator(PALACE_ROOM)
        for bank in range(13):
            at = bank * item_sprites.BANK_SIZE + item_sprites.AP_TILE_OFFSET
            emulator.chr[at:at + 32] = CANDLE
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Candle", 2)}), emulator)
        self.assertEqual(emulator.ap_tiles(0), REGULAR_LOGO)

    def test_own_item_gets_its_palette_and_logo_gets_its_own_back(self) -> None:
        emulator = FakeEmulator(dict(PALACE_ROOM))
        client = Client.Z2RClient()
        ctx = make_ctx({"PALACE1:item1": ("Candle", 1), "WEST_CAVE_HEART_CONTAINER": ("Hammer", 2)})
        run(client, ctx, emulator)
        self.assertEqual(emulator.prg[PALETTE_BYTE], 1)
        emulator.ram.update(CAVE_ROOM)
        run(client, ctx, emulator)
        self.assertEqual(emulator.prg[PALETTE_BYTE], item_sprites.AP_PALETTE)

    def test_other_players_progression_item_uses_the_same_stable_logo_palette(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM)
        ctx = make_ctx({"PALACE1:item1": ("Candle", 2)})
        ctx.locations_info[LOCATION_NAME_TO_ID["PALACE1:item1"]].flags = 0b001  # progression
        run(Client.Z2RClient(), ctx, emulator)
        self.assertEqual(emulator.ap_tiles(0), PROGRESSION_LOGO)
        self.assertEqual(emulator.prg[PALETTE_BYTE], item_sprites.AP_PALETTE)

    def test_other_players_filler_item_uses_the_white_logo(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM)
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Small Key", 2)}, flags=0), emulator)
        self.assertEqual(emulator.ap_tiles(0), item_sprites.solid(LOGO, item_sprites.MINOR_INDEX))

    def test_logo_color_comes_from_the_flags_not_the_name(self) -> None:
        # another game's item: a Z2R minor name doesn't matter, its class does (a trap shows as a regular item)
        for flags, index in ((0, item_sprites.MINOR_INDEX), (0b100, item_sprites.REGULAR_INDEX),
                             (0b011, item_sprites.PROGRESSION_INDEX)):
            with self.subTest(flags=flags):
                emulator = FakeEmulator(PALACE_ROOM)
                ctx = make_ctx({"PALACE1:item1": ("Small Key", 2)}, flags=flags)
                ctx.locations_info[LOCATION_NAME_TO_ID["PALACE1:item1"]].item = 9999  # an id from another game
                run(Client.Z2RClient(), ctx, emulator)
                self.assertEqual(emulator.ap_tiles(0), item_sprites.solid(LOGO, index))

    def test_restart_with_a_recolored_logo_drawn_recolors_from_it(self) -> None:
        # an earlier run left the red logo in the AP tiles; another player's regular item turns it orange
        emulator = FakeEmulator(PALACE_ROOM)
        for bank in range(13):
            at = bank * item_sprites.BANK_SIZE + item_sprites.AP_TILE_OFFSET
            emulator.chr[at:at + 32] = PROGRESSION_LOGO
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Candle", 2)}), emulator)
        self.assertEqual(emulator.ap_tiles(0), REGULAR_LOGO)

    def test_wide_restart_with_a_recolored_logo_drawn_recolors_from_it(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM, wide=True)
        for bank in range(13):
            at = bank * item_sprites.BANK_SIZE + item_sprites.AP_TILE_OFFSET
            emulator.chr[at:at + 32] = PROGRESSION_LOGO
        at = item_sprites.RIGHT_TILE_ADDRESS
        emulator.chr[at:at + 32] = item_sprites.solid(item_sprites.AP_LOGO_RIGHT, item_sprites.PROGRESSION_INDEX)
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Small Key", 2)}, flags=0), emulator)
        self.assertEqual(emulator.ap_tiles(0), item_sprites.solid(LOGO, item_sprites.MINOR_INDEX))
        self.assertEqual(emulator.right_tiles(), item_sprites.solid(item_sprites.AP_LOGO_RIGHT, item_sprites.MINOR_INDEX))

    def test_fixed_tile_rom_draws_the_item_there_and_leaves_the_one_up_tiles(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM, fixed=True)
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Candle", 1)}), emulator)
        at = item_sprites.FIXED_LEFT_ADDRESS
        self.assertEqual(bytes(emulator.chr[at:at + 32]), CANDLE)
        self.assertEqual(emulator.ap_tiles(0), item_sprites.ONE_UP_TILES)
        self.assertEqual(emulator.ap_tiles(12), item_sprites.ONE_UP_TILES)

    def test_fixed_tile_rom_logo_comes_back(self) -> None:
        emulator = FakeEmulator(dict(PALACE_ROOM), fixed=True)
        client = Client.Z2RClient()
        ctx = make_ctx({"PALACE1:item1": ("Candle", 1), "WEST_CAVE_HEART_CONTAINER": ("Hammer", 2)})
        run(client, ctx, emulator)
        emulator.ram.update(CAVE_ROOM)
        run(client, ctx, emulator)
        at = item_sprites.FIXED_LEFT_ADDRESS
        self.assertEqual(bytes(emulator.chr[at:at + 32]), REGULAR_LOGO)

    def test_fixed_tile_rom_restarted_client_restores_the_logo(self) -> None:
        emulator = FakeEmulator(dict(PALACE_ROOM), fixed=True)
        at = item_sprites.FIXED_LEFT_ADDRESS
        emulator.chr[at:at + 32] = CANDLE  # an item was drawn when the old client stopped
        ctx = make_ctx({"WEST_CAVE_HEART_CONTAINER": ("Hammer", 2)})
        emulator.ram.update(CAVE_ROOM)
        run(Client.Z2RClient(), ctx, emulator)
        self.assertEqual(bytes(emulator.chr[at:at + 32]), REGULAR_LOGO)

    def test_jar_uses_the_jars_palette(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM)
        emulator.chr[0x88A0:0x88C0] = CANDLE  # any tiles; only the palette matters here
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Red Magic Jar", 1)}), emulator)
        self.assertEqual(emulator.prg[PALETTE_BYTE], 2)

    def test_old_rom_never_writes_the_right_tile(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM)
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Heart Container", 1)}), emulator)
        self.assertEqual(emulator.right_tiles(), item_sprites.BLANK)

    def test_wide_rom_draws_both_halves(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM, wide=True)
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Heart Container", 1)}), emulator)
        expected = item_sprites.wide_item_sprite("Heart Container", {0x1800: HEART_HALF})
        for bank in range(13):
            self.assertEqual(emulator.ap_tiles(bank), expected[:32])
        self.assertEqual(emulator.right_tiles(), expected[32:])

    def test_wide_rom_narrow_item_blanks_the_right_half(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM, wide=True)
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Candle", 1)}), emulator)
        self.assertEqual(emulator.ap_tiles(0), CANDLE)
        self.assertEqual(emulator.right_tiles(), item_sprites.BLANK)

    def test_wide_rom_logo_comes_back_whole(self) -> None:
        emulator = FakeEmulator(dict(PALACE_ROOM), wide=True)
        client = Client.Z2RClient()
        ctx = make_ctx({"PALACE1:item1": ("Heart Container", 1), "WEST_CAVE_HEART_CONTAINER": ("Hammer", 2)})
        run(client, ctx, emulator)
        emulator.ram.update(CAVE_ROOM)
        run(client, ctx, emulator)
        self.assertEqual(emulator.ap_tiles(0), REGULAR_LOGO)
        self.assertEqual(emulator.right_tiles(), item_sprites.solid(item_sprites.AP_LOGO_RIGHT, item_sprites.REGULAR_INDEX))

    def test_wide_rom_restarted_client_restores_the_logo(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM, wide=True)
        drawn = item_sprites.wide_item_sprite("Heart Container", {0x1800: HEART_HALF})
        for bank in range(13):
            at = bank * item_sprites.BANK_SIZE + item_sprites.AP_TILE_OFFSET
            emulator.chr[at:at + 32] = drawn[:32]
        emulator.chr[item_sprites.RIGHT_TILE_ADDRESS:item_sprites.RIGHT_TILE_ADDRESS + 32] = drawn[32:]
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Candle", 2)}), emulator)
        self.assertEqual(emulator.ap_tiles(0), REGULAR_LOGO)
        self.assertEqual(emulator.right_tiles(), item_sprites.solid(item_sprites.AP_LOGO_RIGHT, item_sprites.REGULAR_INDEX))

    def test_rom_without_the_palette_code_still_draws_the_item(self) -> None:
        emulator = FakeEmulator(PALACE_ROOM, palette_table=False)
        run(Client.Z2RClient(), make_ctx({"PALACE1:item1": ("Candle", 1)}), emulator)
        self.assertEqual(emulator.ap_tiles(0), CANDLE)
        self.assertEqual(emulator.prg[PALETTE_BYTE], 0)


if __name__ == "__main__":
    unittest.main()
