import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from .. import Client
from ..Items import ITEM_NAME_TO_ID
from ..Locations import LOCATION_NAME_TO_ID


class FakeRam:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values
        self.writes: list[tuple[int, list[int], str]] = []

    async def read(self, _ctx, reads):
        return [bytes(self.values.get(address + i, 0) for i in range(size)) for address, size, _domain in reads]

    async def guarded_write(self, _ctx, writes, _guards):
        self.writes += writes
        return True


class TestContainers(unittest.TestCase):
    def run_check(self, received: list[str], ram: dict[int, int], sender: int = 2,
                  item_times: bool = False) -> FakeRam:
        fake = FakeRam(ram)
        names = {ITEM_NAME_TO_ID[name]: name for name in received}
        ctx = SimpleNamespace(
            bizhawk_ctx=None, game="Z2R", team=0, slot=1, stored_data={}, set_notify=lambda *keys: None,
            items_received=[SimpleNamespace(item=ITEM_NAME_TO_ID[name], player=sender) for name in received],
            item_names=SimpleNamespace(lookup_in_game=lambda item, game: names[item]),
            slot_data={"start_magic_containers": 4, "start_heart_containers": 4,
                       "new_kasuto_basement_requirement": 8})
        client = Client.Z2RClient()
        client.guards = []
        client.item_times = item_times
        with mock.patch.object(Client.bizhawk, "read", fake.read), \
                mock.patch.object(Client.bizhawk, "guarded_write", fake.guarded_write):
            asyncio.run(client.received_items_check(ctx, b""))
        return fake

    def mailbox(self, fake: FakeRam) -> list[int] | None:
        return {address: value for address, value, _ in fake.writes}.get(Client.ITEM_TIME_MAILBOX_ADDRESS)

    def test_new_items_are_flagged_for_their_times(self) -> None:
        # own finds are delivered by the client too, so they are timed like items from others
        for sender in (1, 2):
            fake = self.run_check(["Glove", "Reflect Spell", "Candle"], {0x0783: 4, 0x0784: 4}, sender=sender,
                                  item_times=True)
            self.assertEqual(self.mailbox(fake), [1 << 0 | 1 << 6])

    def test_a_flag_the_game_has_not_read_yet_is_kept(self) -> None:
        fake = self.run_check(["Raft"], {0x0783: 4, 0x0784: 4, Client.ITEM_TIME_MAILBOX_ADDRESS: 1},
                              item_times=True)
        self.assertEqual(self.mailbox(fake), [0b11])

    def test_held_and_starting_items_are_not_timed(self) -> None:
        held = self.run_check(["Glove", "Raft"], {0x0783: 4, 0x0784: 4, 0x0786: 1}, item_times=True)
        self.assertEqual(self.mailbox(held), [1 << 1])
        starting = self.run_check(["Glove"], {0x0783: 4, 0x0784: 4}, sender=0, item_times=True)
        self.assertIsNone(self.mailbox(starting))

    def test_rom_without_item_times_gets_no_flags(self) -> None:
        # on an older ROM the mailbox byte means nothing, so it is left alone
        fake = self.run_check(["Glove"], {0x0783: 4, 0x0784: 4})
        self.assertIsNone(self.mailbox(fake))

    def test_magic_container_refills_magic(self) -> None:
        fake = self.run_check(["Magic Container"], {0x0783: 4})
        written = {address: value for address, value, _ in fake.writes}
        self.assertEqual(written[0x0783], [5])
        self.assertEqual(written[Client.MAGIC_REFILL_ADDRESS], [5 << 4])

    def test_heart_container_refills_life(self) -> None:
        fake = self.run_check(["Heart Container"], {0x0784: 4, 0x0783: 4})
        written = {address: value for address, value, _ in fake.writes}
        self.assertEqual(written[0x0784], [5])
        self.assertEqual(written[Client.LIFE_REFILL_ADDRESS], [0xF0])
        self.assertNotIn(Client.MAGIC_REFILL_ADDRESS, written)

    def test_no_refill_when_nothing_was_added(self) -> None:
        fake = self.run_check(["Magic Container", "Heart Container"], {0x0783: 5, 0x0784: 5})
        self.assertEqual(fake.writes, [])

    def test_new_item_plays_item_get_fanfare(self) -> None:
        fake = self.run_check(["Heart Container"], {0x0784: 4, 0x0783: 4})
        written = {address: value for address, value, _ in fake.writes}
        self.assertEqual(written[Client.MUSIC_REQUEST_ADDRESS], [Client.ITEM_GET_FANFARE])

    def test_crystal_fanfare_is_not_interrupted(self) -> None:
        # interrupting it soft locks the game: Link stays frozen at the statue with no refill
        fake = self.run_check(["Reflect Spell"], {Client.CURRENT_MUSIC_ADDRESS: 0x40, Client.WORLD_ADDRESS: 3})
        written = {address: value for address, value, _ in fake.writes}
        self.assertIn(0x0780, written)  # still delivered
        self.assertNotIn(Client.MUSIC_REQUEST_ADDRESS, written)

    def test_great_palace_music_does_not_block_the_fanfare(self) -> None:
        fake = self.run_check(["Reflect Spell"], {Client.CURRENT_MUSIC_ADDRESS: 0x40,
                                                  Client.WORLD_ADDRESS: Client.GREAT_PALACE_WORLD})
        written = {address: value for address, value, _ in fake.writes}
        self.assertEqual(written[Client.MUSIC_REQUEST_ADDRESS], [Client.ITEM_GET_FANFARE])

    def test_own_item_plays_no_fanfare(self) -> None:
        # you picked it up yourself, so the game already played its fanfare
        fake = self.run_check(["Heart Container"], {0x0784: 4, 0x0783: 4}, sender=1)
        written = {address: value for address, value, _ in fake.writes}
        self.assertIn(0x0784, written)  # still delivered
        self.assertNotIn(Client.MUSIC_REQUEST_ADDRESS, written)

    def test_own_pickup_after_starting_items_plays_no_fanfare(self) -> None:
        # Starting items come from player 0 and are already held, so the first check writes nothing. Your own
        # pickup on the next check must not count those starting items as new items from other players.
        fake = FakeRam({0x0784: 4, 0x0783: 4, 0x0785: 1})
        items = [SimpleNamespace(item=ITEM_NAME_TO_ID["Candle"], player=0)]
        names = {ITEM_NAME_TO_ID["Candle"]: "Candle", ITEM_NAME_TO_ID["Heart Container"]: "Heart Container"}
        ctx = SimpleNamespace(
            bizhawk_ctx=None, game="Z2R", team=0, slot=1, stored_data={}, set_notify=lambda *keys: None,
            items_received=items, item_names=SimpleNamespace(lookup_in_game=lambda item, game: names[item]),
            slot_data={"start_magic_containers": 4, "start_heart_containers": 4,
                       "new_kasuto_basement_requirement": 8})
        client = Client.Z2RClient()
        with mock.patch.object(Client.bizhawk, "read", fake.read), \
                mock.patch.object(Client.bizhawk, "guarded_write", fake.guarded_write):
            asyncio.run(client.received_items_check(ctx, b""))
            self.assertEqual(fake.writes, [])
            items.append(SimpleNamespace(item=ITEM_NAME_TO_ID["Heart Container"], player=1))
            asyncio.run(client.received_items_check(ctx, b""))
        written = {address: value for address, value, _ in fake.writes}
        self.assertIn(0x0784, written)
        self.assertNotIn(Client.MUSIC_REQUEST_ADDRESS, written)

    def test_basement_bit_alone_plays_no_fanfare(self) -> None:
        # Starting containers already meet the requirement: only the basement bit is written
        fake = self.run_check(["Magic Container"], {0x0783: 8, 0x0784: 4})
        written = {address: value for address, value, _ in fake.writes}
        self.assertNotIn(Client.MUSIC_REQUEST_ADDRESS, written)


class FakeRom:
    """A "PRG ROM" with text tables in bank 3 and an AP sign placeholder for Mido (west) and Old Kasuto (east)."""
    WEST_TABLE, EAST_TABLE = 0xA000, 0xA100  # CPU addresses in bank 3
    MIDO_SIGN, OLD_KASUTO_SIGN = 0xA200, 0xA300

    def __init__(self, mido_sign: bytes | None = None) -> None:
        self.data = bytearray(0x20000)
        self.put_word(Client.TEXT_TABLE_POINTERS, self.WEST_TABLE)
        self.put_word(Client.TEXT_TABLE_POINTERS + 2, self.EAST_TABLE)
        self.put_word(self.prg(self.WEST_TABLE) + 41 * 2, self.MIDO_SIGN)
        self.put_word(self.prg(self.EAST_TABLE) + (94 - 52) * 2, self.OLD_KASUTO_SIGN)
        self.put(self.MIDO_SIGN, mido_sign or Client.legacy_sign_bytes("AP$ITEM", 4))
        self.put(self.OLD_KASUTO_SIGN, Client.legacy_sign_bytes("AP$ITEM", 8))
        self.writes: list[tuple[int, bytes, str]] = []

    @staticmethod
    def prg(cpu: int) -> int:
        return Client.BANK3_PRG + cpu - 0x8000

    def put_word(self, offset: int, value: int) -> None:
        self.data[offset:offset + 2] = value.to_bytes(2, "little")

    def put(self, cpu: int, data: bytes) -> None:
        self.data[self.prg(cpu):self.prg(cpu) + len(data)] = data

    def sign(self, cpu: int) -> bytes:
        return bytes(self.data[self.prg(cpu):self.prg(cpu) + Client.SIGN_SIZE])

    async def read(self, _ctx, reads):
        return [bytes(self.data[address:address + size]) for address, size, _domain in reads]

    async def write(self, _ctx, writes):
        for address, data, _domain in writes:
            self.data[address:address + len(data)] = data
        self.writes += writes


class TestTownSigns(unittest.TestCase):
    MIDO = "WEST_TOWN_MIDO:wizard"
    OLD_KASUTO = "EAST_TOWN_OLD_KASUTO:wizard"

    def make_ctx(self, items: dict[str, tuple[int, str]]) -> SimpleNamespace:
        """items: location name -> (player, item name)"""
        ids = {name: ITEM_NAME_TO_ID.get(item, 999) for name, (_player, item) in items.items()}
        names = {ITEM_NAME_TO_ID[item]: item for _player, item in items.values() if item in ITEM_NAME_TO_ID}
        sent = []

        async def send_msgs(msgs):
            sent.extend(msgs)

        return SimpleNamespace(
            bizhawk_ctx=None, slot=1, sent=sent, send_msgs=send_msgs,
            # Mido is town type 4 (bit 0x01), Old Kasuto town type 8 (bit 0x10)
            slot_data={"locations": {self.MIDO: {"address": 0x077A, "mask": 0x01, "collected": 1},
                                     self.OLD_KASUTO: {"address": 0x077A, "mask": 0x10, "collected": 1},
                                     "WEST_GRASS": {"address": 0x0600, "mask": 0x01, "collected": 0}}},
            locations_info={LOCATION_NAME_TO_ID[name]: SimpleNamespace(player=player, item=ids[name])
                            for name, (player, _item) in items.items()},
            player_names={1: "Gob-Z2R", 2: "Gob-DWR", 3: "A_Very_Long_Player_"},
            item_names=SimpleNamespace(lookup_in_game=lambda item, game: names[item],
                                       lookup_in_slot=lambda item, player: names[item]))

    def run_check(self, ctx, rom: FakeRom, client: Client.Z2RClient | None = None) -> Client.Z2RClient:
        client = client or Client.Z2RClient()
        with mock.patch.object(Client.bizhawk, "read", rom.read), mock.patch.object(Client.bizhawk, "write", rom.write), mock.patch.object(Client.bizhawk, "guarded_write", lambda _c, w, _g: rom.write(_c, w)):
            asyncio.run(client.sign_check(ctx))
        return client

    def test_own_item_is_named_and_other_players_item_shows_owner(self) -> None:
        rom = FakeRom()
        ctx = self.make_ctx({self.MIDO: (1, "Hammer"), self.OLD_KASUTO: (2, "Hammer")})
        self.run_check(ctx, rom)
        self.assertEqual(rom.sign(FakeRom.MIDO_SIGN), Client.sign_bytes("HAMMER$TOWN", 4))
        self.assertEqual(rom.sign(FakeRom.OLD_KASUTO_SIGN), Client.sign_bytes("GOB-DWR$HAMMER", 8))
        self.assertEqual(len(rom.writes), 2)

    def test_longest_name_fits_and_keeps_town_byte(self) -> None:
        rom = FakeRom()
        self.run_check(self.make_ctx({self.MIDO: (1, "Magic Container"), self.OLD_KASUTO: (1, "Thunder Spell")}), rom)
        mido = rom.sign(FakeRom.MIDO_SIGN)
        self.assertEqual(mido, Client.encode_text("MAGIC$CONTAINER$TOWN") + bytes([4]))
        self.assertEqual(rom.sign(FakeRom.OLD_KASUTO_SIGN)[-1], 8)

    def test_scouts_first_then_writes(self) -> None:
        rom = FakeRom()
        ctx = self.make_ctx({})
        client = self.run_check(ctx, rom)
        self.assertEqual(ctx.sent, [{"cmd": "LocationScouts", "create_as_hint": 0,
                                     "locations": [LOCATION_NAME_TO_ID[self.MIDO],
                                                   LOCATION_NAME_TO_ID[self.OLD_KASUTO]]}])
        self.assertEqual(rom.writes, [])
        self.run_check(ctx, rom, client)
        self.assertEqual(len(ctx.sent), 1)  # does not scout again while waiting for the reply

    def test_rom_without_placeholder_is_left_alone(self) -> None:
        old_sign = Client.encode_text("JUMP$SPELL$TOWN").ljust(Client.SIGN_SIZE, b"\x00")
        rom = FakeRom(mido_sign=old_sign)
        self.run_check(self.make_ctx({self.MIDO: (1, "Hammer"), self.OLD_KASUTO: (1, "Raft")}), rom)
        self.assertEqual(rom.sign(FakeRom.MIDO_SIGN), old_sign)
        self.assertEqual(rom.sign(FakeRom.OLD_KASUTO_SIGN), Client.sign_bytes("RAFT$TOWN", 8))

    def test_signs_rewritten_after_rom_reload(self) -> None:
        rom = FakeRom()
        ctx = self.make_ctx({self.MIDO: (1, "Hammer"), self.OLD_KASUTO: (1, "Raft")})
        client = self.run_check(ctx, rom)
        rom.put(FakeRom.MIDO_SIGN, Client.legacy_sign_bytes("AP$ITEM", 4))  # the ROM was reloaded
        client.next_sign_check = 0
        self.run_check(ctx, rom, client)
        self.assertEqual(rom.sign(FakeRom.MIDO_SIGN), Client.sign_bytes("HAMMER$TOWN", 4))

    def test_long_player_name_is_cut_to_fit(self) -> None:
        rom = FakeRom()
        self.run_check(self.make_ctx({self.MIDO: (3, "Hammer"), self.OLD_KASUTO: (1, "Raft")}), rom)
        self.assertEqual(rom.sign(FakeRom.MIDO_SIGN), Client.sign_bytes("A_VERY_LONG$HAMMER", 4))


    def test_scouts_again_after_a_reconnect(self) -> None:
        rom = FakeRom()
        ctx = self.make_ctx({})
        client = self.run_check(ctx, rom)
        self.assertEqual(len(ctx.sent), 1)
        client.signs_scout_retry = 0.0  # the retry time has passed and no reply came (a reconnect forgets them)
        self.run_check(ctx, rom, client)
        self.assertEqual(len(ctx.sent), 2)

    def test_slot_data_without_locations_does_nothing(self) -> None:
        rom = FakeRom()
        ctx = self.make_ctx({})
        ctx.slot_data = {}
        self.run_check(ctx, rom)
        self.assertEqual(rom.writes, [])


class TestShortItemName(unittest.TestCase):
    def test_short_names_fit_two_lines(self) -> None:
        self.assertEqual(Client.short_item_name("Progressive Sword"), "SWORD")
        self.assertEqual(Client.short_item_name("Bow"), "BOW")
        self.assertEqual(Client.short_item_name("Ice Beam"), "ICE BEAM")
        self.assertEqual(Client.short_item_name("Link's Bow"), "LINKS BOW")

    def test_too_many_words_gives_none(self) -> None:
        self.assertIsNone(Client.short_item_name("Alpha Bravo Charlie Delta Echo Foxtrot"))
        self.assertIsNone(Client.short_item_name("★"))


class TestHelpfulHints(unittest.TestCase):
    """Two hints: text 32 (west table) and texts 85 and 97 (east table, one NPC with two messages)."""
    HINT_A, HINT_B = 0xA400, 0xA500  # CPU addresses in bank 3
    GRASS, PALACE = "WEST_GRASS", "PALACE1:item1"

    def make_rom(self) -> FakeRom:
        rom = FakeRom()
        rom.put_word(rom.prg(FakeRom.WEST_TABLE) + 32 * 2, self.HINT_A)
        rom.put_word(rom.prg(FakeRom.EAST_TABLE) + (85 - 52) * 2, self.HINT_B)
        rom.put_word(rom.prg(FakeRom.EAST_TABLE) + (97 - 52) * 2, self.HINT_B)
        rom.put(self.HINT_A, Client.hint_bytes("AP HINT", 0))
        rom.put(self.HINT_B, Client.hint_bytes("AP HINT", 1))
        return rom

    def hint(self, rom: FakeRom, cpu: int) -> bytes:
        return bytes(rom.data[rom.prg(cpu):rom.prg(cpu) + Client.HINT_SIZE])

    def make_ctx(self, items: dict[str, tuple[int, str, int]]) -> SimpleNamespace:
        """items: location name -> (player, item name, flags)"""
        ids = {name: ITEM_NAME_TO_ID.get(item, 999) for name, (_p, item, _f) in items.items()}
        own = {ITEM_NAME_TO_ID[item]: item for _p, item, _f in items.values() if item in ITEM_NAME_TO_ID}
        other = {999: [item for _p, item, _f in items.values() if item not in ITEM_NAME_TO_ID][0]} \
            if any(item not in ITEM_NAME_TO_ID for _p, item, _f in items.values()) else {}
        sent = []

        async def send_msgs(msgs):
            sent.extend(msgs)

        return SimpleNamespace(
            bizhawk_ctx=None, slot=1, seed_name="12345", sent=sent, send_msgs=send_msgs,
            player_names={1: "GOB-Z2R", 2: "TETRA"},
            slot_data={"locations": {}, "hint_slots": [[32], [85, 97]],
                       "hint_places": {self.GRASS: "go west to$find the$", self.PALACE: "horsehead$neighs$with the$"}},
            locations_info={LOCATION_NAME_TO_ID[name]: SimpleNamespace(player=player, item=ids[name], flags=flags)
                            for name, (player, _item, flags) in items.items()},
            item_names=SimpleNamespace(lookup_in_game=lambda item, game: own[item],
                                       lookup_in_slot=lambda item, slot: other[item]))

    def run_check(self, ctx, rom: FakeRom, client: Client.Z2RClient | None = None) -> Client.Z2RClient:
        client = client or Client.Z2RClient()
        with mock.patch.object(Client.bizhawk, "read", rom.read), mock.patch.object(Client.bizhawk, "write", rom.write), mock.patch.object(Client.bizhawk, "guarded_write", lambda _c, w, _g: rom.write(_c, w)):
            asyncio.run(client.hint_check(ctx))
        return client

    def written(self, rom: FakeRom) -> set[bytes]:
        return {self.hint(rom, self.HINT_A)[:-1], self.hint(rom, self.HINT_B)[:-1]}

    def test_hints_name_own_and_other_items(self) -> None:
        rom = self.make_rom()
        self.run_check(self.make_ctx({self.GRASS: (1, "Hammer", 1), self.PALACE: (2, "Progressive Sword", 1)}), rom)
        expected = {Client.hint_bytes("GRASS TILE$HAS YOUR$HAMMER", 0)[:-1],
                    Client.hint_bytes("P1 HAS$TETRAS$SWORD", 1)[:-1]}
        self.assertEqual(self.written(rom), expected)
        self.assertEqual(self.hint(rom, self.HINT_A)[-1], 0x80)
        self.assertEqual(self.hint(rom, self.HINT_B)[-1], 0x81)

    def test_long_other_name_falls_back_to_ap_item(self) -> None:
        rom = self.make_rom()
        self.run_check(self.make_ctx({self.GRASS: (1, "Hammer", 1),
                                      self.PALACE: (2, "Alpha Bravo Charlie Delta Echo Foxtrot", 1)}), rom)
        self.assertIn(Client.hint_bytes("P1 HAS$TETRAS AP$ITEM", 1)[:-1], self.written(rom))

    def test_progression_items_are_hinted_first(self) -> None:
        rom = self.make_rom()
        rom.put(self.HINT_B, Client.hint_bytes("I KNOW$NOTHING", 1))  # only one placeholder left: hint A
        ctx = self.make_ctx({self.GRASS: (1, "Small Key", 0), self.PALACE: (1, "Hammer", 1)})
        ctx.slot_data["hint_slots"] = [[32]]
        self.run_check(ctx, rom)
        self.assertEqual(self.hint(rom, self.HINT_A), Client.hint_bytes("P1 HAS YOUR$HAMMER", 0))

    def test_other_text_is_left_alone(self) -> None:
        rom = self.make_rom()
        rom.put(self.HINT_A, Client.encode_text("I KNOW$NOTHING").ljust(Client.HINT_SIZE, b"\x00"))
        before = self.hint(rom, self.HINT_A)
        self.run_check(self.make_ctx({self.GRASS: (1, "Hammer", 1), self.PALACE: (1, "Raft", 1)}), rom)
        self.assertEqual(self.hint(rom, self.HINT_A), before)

    def test_restarted_client_updates_its_own_hints_without_warning(self) -> None:
        # a client wrote these hints, then restarted (forgetting what it wrote) while the game kept the text
        rom = self.make_rom()
        rom.put(self.HINT_A, Client.hint_bytes("OLD$HINT", 0))
        rom.put(self.HINT_B, Client.hint_bytes("OLD$HINT", 1))
        client = Client.Z2RClient()
        with self.assertNoLogs(Client.logger, level="WARNING"):
            self.run_check(self.make_ctx({self.GRASS: (1, "Hammer", 1), self.PALACE: (1, "Raft", 1)}), rom, client)
        self.assertNotIn(Client.hint_bytes("OLD$HINT", 0), {self.hint(rom, self.HINT_A), self.hint(rom, self.HINT_B)})
        self.assertNotIn(Client.hint_bytes("OLD$HINT", 1), {self.hint(rom, self.HINT_A), self.hint(rom, self.HINT_B)})

    def test_text_with_another_slots_marker_is_left_alone(self) -> None:
        rom = self.make_rom()
        other = Client.hint_bytes("OLD$HINT", 5)
        rom.put(self.HINT_A, other)
        self.run_check(self.make_ctx({self.GRASS: (1, "Hammer", 1), self.PALACE: (1, "Raft", 1)}), rom)
        self.assertEqual(self.hint(rom, self.HINT_A), other)

    def test_no_hint_slots_does_nothing(self) -> None:
        rom = self.make_rom()
        ctx = self.make_ctx({self.GRASS: (1, "Hammer", 1)})
        ctx.slot_data["hint_slots"] = []
        self.run_check(ctx, rom)
        self.assertEqual(rom.writes, [])
        self.assertEqual(ctx.sent, [])


    def test_every_text_index_of_a_hint_npc_is_written(self) -> None:
        rom = self.make_rom()
        self.run_check(self.make_ctx({self.GRASS: (1, "Hammer", 1), self.PALACE: (1, "Raft", 1)}), rom)
        written = {address for address, _data, _domain in rom.writes}
        self.assertGreaterEqual(len(written), 2)

    def test_hints_use_the_seed_name_the_server_reported(self) -> None:
        client = Client.Z2RClient()
        orders = set()
        for seed in ("a1", "b2", "c3", "d4", "e5", "f6", "g7", "h8"):
            ctx = self.make_ctx({self.GRASS: (1, "Hammer", 1), self.PALACE: (1, "Raft", 1)})
            ctx.seed_name = None
            ctx.server_seed_name = seed
            orders.add(tuple(client.choose_hints(ctx, 2)))
        self.assertGreater(len(orders), 1)

class TestOtherPlayerSigns(unittest.TestCase):
    def test_short_form_keeps_the_full_name(self) -> None:
        self.assertEqual(Client.other_player_sign(3, "Gob-ZORA", "Magic Container"), "GOB-ZORA$MC")
        self.assertEqual(Client.other_player_sign(3, "Gob-ZORA", "Boomerang Upgrade"), "GOB-ZORA$BOOMER UP")
        self.assertEqual(Client.other_player_sign(2, "Gob-DWR", "Power Bracelet"), "GOB-DWR$PB")

    def test_zora_level_items_use_their_short_form(self) -> None:
        self.assertEqual(Client.other_player_sign(2, "Gob-ZORA", "Level 3 Triforce"), "GOB-ZORA$TRIFORCE 3")
        self.assertEqual(Client.other_player_sign(2, "Gob-ZORA", "Level 9 Compass"), "GOB-ZORA$COMPASS 9")
        # a long player name leaves 8 characters: the tiny form instead of AP$ITEM
        self.assertEqual(Client.other_player_sign(2, "ABCDEFGHIJK", "Level 3 Triforce"), "ABCDEFGHIJK$TRIFRC 3")
        self.assertEqual(Client.other_player_sign(2, "ABCDEFGHIJK", "Level 9 Compass"), "ABCDEFGHIJK$COMPAS 9")
        self.assertEqual(Client.other_player_sign(2, "ABCDEFGHI", "Level 3 Triforce"), "ABCDEFGHI$TRIFORCE 3")

    def test_full_item_name_used_when_it_fits(self) -> None:
        self.assertEqual(Client.other_player_sign(2, "Gob-DWR", "Hammer"), "GOB-DWR$HAMMER")

    def test_short_or_unusable_name_uses_player_number(self) -> None:
        self.assertEqual(Client.other_player_sign(6, "üü", "1-Up"), "P6$1-UP")

    def test_every_line_fits(self) -> None:
        for name in ("A_Very_Long_Player_Name", "Gob-ZORA", "x"):
            for item in ("Stones of Sunlight", "Magical Boomerang", "Erdrick's Token", "Progressive Sword"):
                text = Client.other_player_sign(9, name, item)
                self.assertIsNotNone(Client.sign_bytes(text, 1), text)
                self.assertTrue(all(len(line) <= Client.SIGN_LINE_LENGTH for line in text.split("$")), text)
