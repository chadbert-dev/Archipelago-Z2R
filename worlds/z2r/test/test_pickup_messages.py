import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from .. import Client


class PickupMessageTextTest(unittest.TestCase):
    def test_own_item(self) -> None:
        self.assertEqual(Client.pickup_message("Hammer", "Gob-Z2R", True), "GOT YOUR HAMMER")

    def test_other_players_item(self) -> None:
        self.assertEqual(Client.pickup_message("Silver Arrow", "Tetra", False), "SENT SILVER ARROW TO TETRA")

    def test_long_names_are_cut_to_fit(self) -> None:
        text = Client.pickup_message("Progressive Ultra Mega Upgrade", "A Very Long Player", False)
        self.assertLessEqual(len(text), Client.HUD_MESSAGE_WIDTH)
        self.assertEqual(text, "SENT AP ITEM TO A VERY LONG")

    def test_apostrophes_are_dropped(self) -> None:
        self.assertEqual(Client.pickup_message("Erdrick's Token", "Gob", False), "SENT ERDRICKS TOKEN TO GOB")

    def test_long_item_uses_its_short_form(self) -> None:
        self.assertEqual(Client.pickup_message("Fighter's Ring", "Gob-DWR", False), "SENT F-RING TO GOB-DWR")

    def test_long_item_without_short_form_is_cut_at_a_word(self) -> None:
        self.assertEqual(Client.pickup_message("Golden Feather Cape", "Gob-DWR", False), "SENT GOLDEN TO GOB-DWR")

    def test_hud_text_keeps_only_hud_glyphs(self) -> None:
        self.assertEqual(Client.hud_message_bytes("GOT A!?,_.B"), Client.hud_message_bytes("GOT A     B"))

    def test_long_place_and_owner_hint_stays_four_lines(self) -> None:
        for owner in ("ABCDEFGHIJ", "GOB Z2R", None):
            text = Client.hint_sentence("NABOORU FOUNTAIN", "Hammer", owner)
            self.assertLessEqual(len(text.split("$")), 4, text)

    def test_every_place_hint_fits_four_lines(self) -> None:
        from ..place_names import PLACE_NAMES
        for place in set(PLACE_NAMES.values()):
            for owner in ("ABCDEFGHIJ", None):
                with self.subTest(place=place, owner=owner):
                    text = Client.hint_sentence(place, "Progressive Ultra Mega Upgrade", owner)
                    self.assertLessEqual(len(text.split("$")), 4, text)
                    self.assertTrue(all(len(line) <= 11 for line in text.split("$")), text)

    def test_progressive_upgrade_is_not_doubled(self) -> None:
        self.assertNotIn("UPGRD$UPGRD", Client.short_item_name("Progressive Sword Upgrade") or "")

    def test_item_too_long_for_a_word_cut_is_ap_item(self) -> None:
        self.assertEqual(Client.pickup_message("Supercalifragilistic", "Tetra", False), "SENT AP ITEM TO TETRA")

    def test_dialog_fallback_keeps_ap_item_on_one_line(self) -> None:
        text = Client.item_dialog_text("Alpha Bravo Charlie Delta Echo Foxtrot Golf", "Gob", True)
        self.assertEqual(text, "YOU GOT$YOUR$AP ITEM")

    def test_buffer_entry_layout(self) -> None:
        data = Client.hud_message_bytes("GOT HAMMER")
        self.assertEqual(data[:3], bytes([0x20, 0x22, Client.HUD_MESSAGE_WIDTH]))
        self.assertEqual(len(data), 3 + Client.HUD_MESSAGE_WIDTH + 1)
        self.assertEqual(data[-1], 0xFF)
        self.assertEqual(data[3], ord("G") + 0x99)
        self.assertEqual(data[-2], Client.BLANK_TILE)


class HudMessageCheckTest(unittest.TestCase):
    def make_ctx(self) -> SimpleNamespace:
        sent = []

        async def send_msgs(msgs):
            sent.extend(msgs)

        return SimpleNamespace(bizhawk_ctx=None, missing_locations={5, 3}, checked_locations={4}, sent=sent, send_msgs=send_msgs)

    def run_check(self, client, ctx, mode, now, buffer_free=True) -> list:
        writes = []

        async def guarded_write(_ctx, w, _guards):
            if buffer_free:
                writes.extend(w)
            return buffer_free

        async def display_message(_ctx, text):
            self.flashed.append(text)

        with mock.patch.object(Client.bizhawk, "guarded_write", guarded_write), \
                mock.patch.object(Client.bizhawk, "display_message", display_message), \
                mock.patch.object(Client.time, "monotonic", lambda: now):
            asyncio.run(client.hud_message_check(ctx, mode))
        return writes

    def setUp(self) -> None:
        self.flashed: list[str] = []

    def test_overworld_flashes_each_message_once_then_hud_shows_it(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        # built at run time, as the client builds them (equal tuple literals would be one shared object)
        client.pickup_messages = [tuple(["GOT HAMMER FROM TETRA", None]) for _ in range(2)]
        self.assertEqual(self.run_check(client, ctx, 0x05, 1.0), [])
        self.run_check(client, ctx, 0x05, 2.0)
        self.assertEqual(self.flashed, ["GOT HAMMER FROM TETRA"] * 2)  # same text twice: both shown, each once
        shown = self.run_check(client, ctx, Client.HUD_MODE, 3.0)
        self.assertEqual(shown[0][1][1:], Client.hud_message_bytes("GOT HAMMER FROM TETRA"))

    def test_shows_then_clears_after_the_message_time(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        client.pickup_messages = [("GOT HAMMER", 99.0)]
        shown = self.run_check(client, ctx, Client.HUD_MODE, 100.0)
        entry = Client.hud_message_bytes("GOT HAMMER")
        self.assertEqual(shown[0][0], Client.PPU_BUFFER_LENGTH)
        self.assertEqual(shown[0][1], bytes([len(entry) - 1]) + entry)
        self.assertEqual(self.run_check(client, ctx, Client.HUD_MODE, 100.0 + Client.HUD_MESSAGE_SECONDS - 0.1), [])
        cleared = self.run_check(client, ctx, Client.HUD_MODE, 100.0 + Client.HUD_MESSAGE_SECONDS)
        self.assertEqual(cleared[0][1][1:], Client.hud_message_bytes(""))
        self.assertEqual(client.pickup_messages, [])

    def test_scouts_every_location_once(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        self.run_check(client, ctx, Client.HUD_MODE, 1.0)
        self.run_check(client, ctx, Client.HUD_MODE, 2.0)
        self.assertEqual(ctx.sent, [{"cmd": "LocationScouts", "locations": [3, 4, 5], "create_as_hint": 0}])

    def test_stale_messages_are_dropped(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        client.pickup_messages = [("OLD", 1.0), ("NEW", 20.0)]
        shown = self.run_check(client, ctx, Client.HUD_MODE, 21.0)
        self.assertEqual(shown[0][1][1:], Client.hud_message_bytes("NEW"))

    def test_waiting_messages_show_for_less_time(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        client.pickup_messages = [("ONE", 10.0), ("TWO", 10.0)]
        self.run_check(client, ctx, Client.HUD_MODE, 10.0)
        self.assertEqual(client.hud_message_until, 10.0 + Client.HUD_MESSAGE_SECONDS_BUSY)

    def test_scouts_again_after_a_reconnect(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        ctx.locations_info = {3: object(), 4: object(), 5: object()}
        self.run_check(client, ctx, Client.HUD_MODE, 1.0)
        self.assertEqual(ctx.sent, [])
        ctx.locations_info = {}  # a reconnect forgets them
        self.run_check(client, ctx, Client.HUD_MODE, 2.0)
        self.run_check(client, ctx, Client.HUD_MODE, 5.0)
        self.run_check(client, ctx, Client.HUD_MODE, 12.5)
        self.assertEqual(len(ctx.sent), 2)  # once, then again after SCOUT_RETRY_SECONDS

    def test_room_change_shows_the_message_again(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        client.pickup_messages = [("GOT HAMMER", 10.0)]
        self.run_check(client, ctx, Client.HUD_MODE, 10.0)   # shown
        self.run_check(client, ctx, 0x05, 11.0)              # room change after 1 s
        again = self.run_check(client, ctx, Client.HUD_MODE, 18.0)
        self.assertEqual(again[0][1][1:], Client.hud_message_bytes("GOT HAMMER"))
        self.assertEqual(client.hud_message_until, 18.0 + Client.HUD_MESSAGE_SECONDS - 1.0)

    def test_room_change_near_the_end_still_shows_long_enough_to_read(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        client.pickup_messages = [("GOT HAMMER", 10.0)]
        self.run_check(client, ctx, Client.HUD_MODE, 10.0)
        self.run_check(client, ctx, 0x05, 10.0 + Client.HUD_MESSAGE_SECONDS - 0.5)  # 0.5 s left: still gets the busy time
        self.run_check(client, ctx, Client.HUD_MODE, 30.0)
        self.assertEqual(client.hud_message_until, 30.0 + Client.HUD_MESSAGE_SECONDS_BUSY)

    def test_room_change_after_the_time_is_up_shows_nothing(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        client.pickup_messages = [("GOT HAMMER", 10.0)]
        self.run_check(client, ctx, Client.HUD_MODE, 10.0)
        self.run_check(client, ctx, 0x05, 10.0 + Client.HUD_MESSAGE_SECONDS + 1.5)  # time was up, blank not yet written
        self.assertEqual(self.run_check(client, ctx, Client.HUD_MODE, 30.0), [])
        self.assertIsNone(client.hud_message_until)

    def test_waits_outside_side_view_and_for_a_free_buffer(self) -> None:
        client, ctx = Client.Z2RClient(), self.make_ctx()
        client.guards = []
        client.pickup_messages = [("GOT HAMMER", 1.0)]
        self.assertEqual(self.run_check(client, ctx, 0x05, 1.0), [])
        self.assertEqual(self.run_check(client, ctx, Client.HUD_MODE, 1.0, buffer_free=False), [])
        self.assertEqual(client.pickup_messages, [("GOT HAMMER", 1.0)])

    def test_pickup_text_needs_the_scouted_item(self) -> None:
        client = Client.Z2RClient()
        ctx = SimpleNamespace(slot=1, locations_info={7: SimpleNamespace(item=10, player=2)},
                              item_names=SimpleNamespace(lookup_in_slot=lambda item, player: "Hookshot"),
                              player_names={2: "Tetra"})
        self.assertEqual(client.pickup_text(ctx, 7), "SENT HOOKSHOT TO TETRA")
        self.assertIsNone(client.pickup_text(ctx, 8))


class ItemDialogTest(unittest.TestCase):
    def test_text_is_bounded_to_four_lines(self) -> None:
        for own in (True, False):
            text = Client.item_dialog_text("Progressive Ultra Mega Upgrade", "A Very Long Player", own)
            self.assertLessEqual(len(text.split("$")), 4)
            self.assertIsNotNone(Client.item_text_bytes(text, 0))

    def test_own_item_says_your(self) -> None:
        self.assertEqual(Client.item_dialog_text("Hammer", "Gob", True), "YOU GOT$YOUR$HAMMER")

    def test_own_item_uses_its_sign_name(self) -> None:
        self.assertEqual(Client.item_dialog_text("Magic Container", "Gob", True, "MAGIC$CONTAINER"),
                         "YOU GOT$YOUR$MAGIC$CONTAINER")

    def test_other_players_item(self) -> None:
        self.assertEqual(Client.item_dialog_text("Silver Arrow", "Gob-DWR", False), "YOU SENT$SILVER$ARROW$TO GOB-DWR")

    def test_long_player_name_is_cut_to_the_line(self) -> None:
        self.assertEqual(Client.item_dialog_text("Raft", "A Very Long Player", False), "YOU SENT$RAFT$TO A VERY L")

    def test_bytes_end_with_the_dialog_number(self) -> None:
        self.assertEqual(Client.item_text_bytes("AP ITEM", 7)[-1], 0xC7)
        self.assertEqual(len(Client.item_text_bytes("YOU GOT$YOUR$HAMMER", 3)), Client.ITEM_TEXT_SIZE)


class ItemTextCheckTest(unittest.TestCase):
    ADDRESS = 0xA700

    def make_ctx(self, locations_info) -> SimpleNamespace:
        from ..Locations import LOCATION_NAME_TO_ID
        return SimpleNamespace(
            bizhawk_ctx=None, slot=1, player_names={1: "GOB-Z2R", 2: "TETRA"},
            slot_data={"item_text_slots": {"WEST_GRASS": [21, 4]}},
            locations_info={LOCATION_NAME_TO_ID["WEST_GRASS"]: locations_info} if locations_info else {},
            item_names=SimpleNamespace(lookup_in_game=lambda item, game: "Hammer",
                                       lookup_in_slot=lambda item, player: "Silver Arrow"))

    def run_check(self, ctx, memory, client) -> None:
        async def read(_ctx, reads):
            return [memory[address] for address, _size, _domain in reads]

        async def write(_ctx, writes):
            for address, data, _domain in writes:
                memory[address] = data

        async def addresses(_ctx, indexes):
            return [self.ADDRESS for _ in indexes]

        with mock.patch.object(Client.bizhawk, "read", read), mock.patch.object(Client.bizhawk, "write", write), mock.patch.object(Client.bizhawk, "guarded_write", lambda _c, w, _g: write(_c, w)),                 mock.patch.object(Client.Z2RClient, "text_addresses", staticmethod(addresses)):
            asyncio.run(client.item_text_check(ctx))

    def test_own_item_replaces_the_placeholder(self) -> None:
        memory = {self.ADDRESS: Client.item_text_bytes("AP ITEM", 4)}
        self.run_check(self.make_ctx(SimpleNamespace(player=1, item=99)), memory, Client.Z2RClient())
        self.assertEqual(memory[self.ADDRESS], Client.item_text_bytes("YOU GOT$YOUR$HAMMER", 4))

    def test_other_players_item_replaces_the_placeholder(self) -> None:
        memory = {self.ADDRESS: Client.item_text_bytes("AP ITEM", 4)}
        self.run_check(self.make_ctx(SimpleNamespace(player=2, item=99)), memory, Client.Z2RClient())
        self.assertEqual(memory[self.ADDRESS], Client.item_text_bytes("YOU SENT$SILVER$ARROW$TO TETRA", 4))

    def test_other_text_is_left_alone(self) -> None:
        # text the app didn't leave as a placeholder: no marker byte at the end
        other = Client.encode_text("SOMETHING ELSE").ljust(Client.ITEM_TEXT_SIZE, b"\x00")
        memory = {self.ADDRESS: other}
        self.run_check(self.make_ctx(SimpleNamespace(player=1, item=99)), memory, Client.Z2RClient())
        self.assertEqual(memory[self.ADDRESS], other)

    def test_restarted_client_updates_its_own_text(self) -> None:
        # a client wrote this dialog, then restarted (forgetting what it wrote) while the game kept the text
        earlier = Client.item_text_bytes("SOMETHING ELSE", 4)
        memory = {self.ADDRESS: earlier}
        self.run_check(self.make_ctx(SimpleNamespace(player=1, item=99)), memory, Client.Z2RClient())
        self.assertNotEqual(memory[self.ADDRESS], earlier)
        self.assertEqual(memory[self.ADDRESS][-1], earlier[-1])

    def test_waits_for_the_scout_reply(self) -> None:
        placeholder = Client.item_text_bytes("AP ITEM", 4)
        memory = {self.ADDRESS: placeholder}
        client = Client.Z2RClient()
        self.run_check(self.make_ctx(None), memory, client)
        self.assertEqual(memory[self.ADDRESS], placeholder)
        self.assertEqual(client.next_item_text_check, 0.0)


class ErrorDisplayTest(unittest.TestCase):
    def run_error(self, client, state, now, buffer_free=True):
        writes = []

        async def read(_ctx, reads):
            return [bytes([state[0]]) if size == 1 else bytes(state[1:]) for _a, size, _d in reads]

        async def guarded_write(_ctx, w, _guards):
            if buffer_free:
                writes.extend(w)
            return buffer_free

        with mock.patch.object(Client.bizhawk, "read", read),                 mock.patch.object(Client.bizhawk, "guarded_write", guarded_write),                 mock.patch.object(Client.time, "monotonic", lambda: now):
            asyncio.run(client.show_error_on_hud(SimpleNamespace(bizhawk_ctx=None), "WRONG ROM FOR THIS SEED"))
        return writes

    def test_wrong_rom_shows_on_the_hud_in_side_view(self) -> None:
        client = Client.Z2RClient()
        writes = self.run_error(client, (Client.GAME_EVENT_MAIN_LOOP, Client.HUD_MODE, Client.HUD_MODE), 1.0)
        self.assertEqual(writes[0][1][1:], Client.hud_message_bytes("WRONG ROM FOR THIS SEED"))

    def test_error_repeats_every_few_seconds_not_every_frame(self) -> None:
        client = Client.Z2RClient()
        state = (Client.GAME_EVENT_MAIN_LOOP, Client.HUD_MODE, Client.HUD_MODE)
        self.assertEqual(len(self.run_error(client, state, 1.0)), 1)
        self.assertEqual(self.run_error(client, state, 2.0), [])
        self.assertEqual(len(self.run_error(client, state, 1.0 + Client.ERROR_HUD_SECONDS)), 1)

    def test_no_error_outside_side_view(self) -> None:
        client = Client.Z2RClient()
        self.assertEqual(self.run_error(client, (Client.GAME_EVENT_MAIN_LOOP, 0x05, 0x05), 1.0), [])

    def test_missing_slots_are_reported_once(self) -> None:
        client = Client.Z2RClient()
        with self.assertLogs("Client", level="WARNING") as logs:
            client.note_missing_slots("hint")
            client.note_missing_slots("item dialog")
        self.assertEqual(len(logs.records), 1)


class ReceivedItemMessageTest(unittest.TestCase):
    KEY = "z2r_hud_seen_0_1"

    def setUp(self) -> None:
        self.sent = []

        async def send_msgs(msgs):
            self.sent.extend(msgs)

        self.ctx = SimpleNamespace(
            slot=1, team=0, items_received=[], stored_data={self.KEY: None},
            set_notify=lambda *keys: None, send_msgs=send_msgs,
            bizhawk_ctx=None, missing_locations=set(), checked_locations=set(),
            item_names=SimpleNamespace(lookup_in_slot=lambda item, slot: f"ITEM{item}"),
            player_names={2: "Tetra", 1: "Gob-Z2R", 3: "Gob-DWR"},
        )
        self.client = Client.Z2RClient()

    def announce(self) -> list[str]:
        asyncio.run(self.client.announce_received(self.ctx))
        return [entry[0] for entry in self.client.pickup_messages]

    def show(self, now: float) -> None:
        """One HUD tick in side view with a free PPU buffer: writes the next queued message."""
        async def guarded_write(_ctx, _w, _guards):
            return True

        self.client.guards = []
        with mock.patch.object(Client.bizhawk, "guarded_write", guarded_write), \
                mock.patch.object(Client.time, "monotonic", lambda: now):
            asyncio.run(self.client.hud_message_check(self.ctx, Client.HUD_MODE))

    def seen_sets(self) -> list:
        return [m["operations"] for m in self.sent if m.get("cmd") == "Set"]

    def test_received_message_text(self) -> None:
        self.assertEqual(Client.received_message("Silver Arrow", "Tetra"), "GOT SILVER ARROW FROM TETRA")

    def test_waits_for_the_servers_count(self) -> None:
        self.ctx.stored_data = {}
        self.ctx.items_received = [SimpleNamespace(item=5, player=2)]
        self.assertEqual(self.announce(), [])
        self.assertEqual(self.sent, [])

    def test_item_that_arrived_while_away_is_shown(self) -> None:
        self.ctx.items_received = [SimpleNamespace(item=15, player=3)]  # sent while DWR was being played
        self.assertEqual(self.announce(), ["GOT ITEM15 FROM GOB-DWR"])
        self.assertEqual(self.seen_sets(), [])  # not counted until it is on screen
        self.show(1.0)
        self.assertEqual(self.seen_sets(), [[{"operation": "max", "value": 1}]])

    def test_message_not_shown_before_a_switch_shows_next_time(self) -> None:
        self.ctx.items_received = [SimpleNamespace(item=15, player=2)]
        self.announce()                     # queued, but the player leaves before reaching side view
        self.client = Client.Z2RClient()    # a new connection after switching back
        self.assertEqual(self.announce(), ["GOT ITEM15 FROM TETRA"])

    def test_each_message_counts_as_it_shows(self) -> None:
        self.ctx.items_received = [SimpleNamespace(item=5, player=2), SimpleNamespace(item=6, player=1),
                                   SimpleNamespace(item=7, player=2), SimpleNamespace(item=8, player=1)]
        self.announce()
        self.show(1.0)
        self.assertEqual(self.ctx.stored_data[self.KEY], 1)
        self.show(1.0 + Client.HUD_MESSAGE_SECONDS_BUSY)  # clears the first
        self.show(2.0 + Client.HUD_MESSAGE_SECONDS_BUSY)
        self.assertEqual(self.ctx.stored_data[self.KEY], 4)  # the last message covers the own find after it

    def test_items_already_shown_are_not_shown_again(self) -> None:
        self.ctx.stored_data[self.KEY] = 2
        self.ctx.items_received = [SimpleNamespace(item=5, player=2), SimpleNamespace(item=6, player=2)]
        self.assertEqual(self.announce(), [])

    def test_new_item_is_queued_once(self) -> None:
        self.announce()
        self.ctx.items_received.append(SimpleNamespace(item=5, player=2))
        self.announce()
        self.assertEqual(self.announce(), ["GOT ITEM5 FROM TETRA"])

    def test_starting_item_says_started_with(self) -> None:
        self.assertEqual(Client.received_message("Candle", ""), "STARTED WITH CANDLE")
        self.assertLessEqual(len(Client.received_message("Progressive Ultra Mega Upgrade", "")), Client.HUD_MESSAGE_WIDTH)

    def test_server_given_item_says_started_with(self) -> None:
        self.ctx.player_names[0] = "Archipelago"
        self.ctx.items_received = [SimpleNamespace(item=7, player=0)]
        self.assertEqual(self.announce(), ["STARTED WITH ITEM7"])

    def test_own_world_item_is_not_queued(self) -> None:
        self.ctx.items_received = [SimpleNamespace(item=5, player=1)]
        self.assertEqual(self.announce(), [])
        self.assertEqual(self.ctx.stored_data[self.KEY], 1)

    def test_many_at_once_become_one_count(self) -> None:
        self.ctx.items_received = [SimpleNamespace(item=i, player=2) for i in range(7)]
        self.assertEqual(self.announce(), ["GOT 7 ITEMS FROM OTHERS"])

    def test_many_starting_items_are_not_from_others(self) -> None:
        self.ctx.items_received = [SimpleNamespace(item=i, player=0) for i in range(6)]
        self.assertEqual(self.announce(), ["GOT 6 STARTING ITEMS"])
        self.assertEqual(self.client.pickup_messages[0][2], 6)

    def test_starting_and_other_counts_are_split(self) -> None:
        self.ctx.items_received = [SimpleNamespace(item=i, player=0) for i in range(3)]             + [SimpleNamespace(item=i, player=2) for i in range(3)]
        self.assertEqual(self.announce(), ["GOT 3 STARTING ITEMS", "GOT 3 ITEMS FROM OTHERS"])
        self.assertEqual([m[2] for m in self.client.pickup_messages], [3, 6])  # the last carries the total

    def test_count_lines_fit_the_hud_and_use_hud_characters(self) -> None:
        self.ctx.items_received = [SimpleNamespace(item=i, player=0) for i in range(12)]             + [SimpleNamespace(item=i, player=2) for i in range(12)]
        for text in self.announce():
            self.assertLessEqual(len(text), Client.HUD_MESSAGE_WIDTH)
            self.assertTrue(set(text) <= Client.HUD_CHARACTERS)

    def test_received_messages_wait_for_side_view(self) -> None:
        self.ctx.items_received = [SimpleNamespace(item=5, player=2)]
        self.announce()
        self.assertIsNone(self.client.pickup_messages[0][1])  # never dropped as stale


class ServerOfflineTest(unittest.TestCase):
    """The HUD says so when the AP server is lost (the connector's AP OFFLINE only covers losing the client)."""

    def run_watcher(self, client, ctx, now):
        writes = []

        async def read(_ctx, reads):
            return [bytes([Client.GAME_EVENT_MAIN_LOOP]) if size == 1 else bytes([Client.HUD_MODE] * 2)
                    for _a, size, _d in reads]

        async def guarded_write(_ctx, w, _guards):
            writes.extend(w)
            return True

        with mock.patch.object(Client.bizhawk, "read", read),                 mock.patch.object(Client.bizhawk, "guarded_write", guarded_write),                 mock.patch.object(Client.time, "monotonic", lambda: now):
            asyncio.run(client.game_watcher(ctx))
        return writes

    def ctx(self, slot_data):
        return SimpleNamespace(server=None, slot_data=slot_data, bizhawk_ctx=None)

    def test_server_loss_shows_after_a_few_seconds(self) -> None:
        client = Client.Z2RClient()
        ctx = self.ctx({"rom_seed": ""})
        self.assertEqual(self.run_watcher(client, ctx, 10.0), [])  # just lost
        writes = self.run_watcher(client, ctx, 10.0 + Client.SERVER_OFFLINE_AFTER)
        self.assertEqual(writes[0][1][1:], Client.hud_message_bytes(Client.SERVER_OFFLINE_TEXT))
        self.assertTrue(client.offline_hud_shown)

    def test_offline_text_fits_the_hud(self) -> None:
        self.assertLessEqual(len(Client.SERVER_OFFLINE_TEXT), Client.HUD_MESSAGE_WIDTH)
        self.assertTrue(set(Client.SERVER_OFFLINE_TEXT) <= Client.HUD_CHARACTERS)

    def test_nothing_before_the_client_ever_connected(self) -> None:
        client = Client.Z2RClient()
        ctx = self.ctx(None)
        self.run_watcher(client, ctx, 10.0)
        self.assertEqual(self.run_watcher(client, ctx, 100.0), [])

    def test_repeats_not_every_frame(self) -> None:
        client = Client.Z2RClient()
        ctx = self.ctx({})
        self.run_watcher(client, ctx, 10.0)
        self.assertEqual(len(self.run_watcher(client, ctx, 14.0)), 1)
        self.assertEqual(self.run_watcher(client, ctx, 15.0), [])
