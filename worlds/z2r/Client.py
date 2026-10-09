import logging
from typing import TYPE_CHECKING

from NetUtils import ClientStatus

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient
from .Items import CONTAINER_ITEMS, ITEM_TABLE
from .Locations import LOCATION_NAME_TO_ID

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

logger = logging.getLogger("Client")

# The Z2R app writes a 64 byte signature at CPU $FCB0 in bank 7. That is file offset 0x1FCC0, or 0x1FCB0 in
# BizHawk's "PRG ROM" domain, which does not include the 16 byte iNES header.
# Layout: "Z2AP", version, 3 reserved, 16 byte slot name, 32 byte seed text, 4 byte little endian seed hash
SIGNATURE_ADDRESS = 0x1FCB0
SIGNATURE_SIZE = 0x40
SIGNATURE_MAGIC = b"Z2AP"
SIGNATURE_VERSION = 1

# NES CPU RAM, used for everything below
RAM = "RAM"
# Item presence tables, wizard flags and misc flags all live in this range
FLAGS_START = 0x0600
FLAGS_SIZE = 0x0200
# Nonzero bit 7 once the ending sequence has started (GameComplete in the Z2R app's ram.inc)
GAME_COMPLETE_ADDRESS = 0x0128
GAME_COMPLETE_MASK = 0x80
# Items that are spent in game, so they are added one at a time instead of being set. The number already given is
# kept in the server's data storage so a reconnect doesn't give them again.
# name -> (RAM address of the count, maximum the client will raise it to)
CONSUMABLE_ITEMS: dict[str, tuple[int, int]] = {
    "Small Key": (0x0793, 64),
    "1-Up": (0x0700, 99),
}
# 1 while the main game loop is running. Item presence bits read as "collected" while the title screen is up,
# so nothing is read or written unless this is 1.
GAME_EVENT_ADDRESS = 0x076C
GAME_EVENT_MAIN_LOOP = 1


class Z2RClient(BizHawkClient):
    game = "Zelda II: Z2R"
    system = "NES"

    slot_name: str

    def __init__(self) -> None:
        self.slot_name = ""

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        try:
            if await bizhawk.get_memory_size(ctx.bizhawk_ctx, "PRG ROM") < SIGNATURE_ADDRESS + SIGNATURE_SIZE:
                return False
            block = (await bizhawk.read(ctx.bizhawk_ctx, [(SIGNATURE_ADDRESS, SIGNATURE_SIZE, "PRG ROM")]))[0]
        except bizhawk.RequestFailedError:
            return False

        if block[:4] != SIGNATURE_MAGIC or block[4] != SIGNATURE_VERSION:
            return False

        self.slot_name = block[0x08:0x18].split(b"\x00")[0].decode("ascii", errors="replace")
        ctx.game = self.game
        ctx.items_handling = 0b111
        ctx.want_slot_data = True
        return True

    async def set_auth(self, ctx: "BizHawkClientContext") -> None:
        ctx.auth = self.slot_name

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        if ctx.server is None or ctx.server.socket.closed or ctx.slot_data is None:
            return

        try:
            state = await bizhawk.guarded_read(
                ctx.bizhawk_ctx,
                [(FLAGS_START, FLAGS_SIZE, RAM), (GAME_COMPLETE_ADDRESS, 1, RAM)],
                [(GAME_EVENT_ADDRESS, [GAME_EVENT_MAIN_LOOP], RAM)])
            if state is None:
                return  # not in the main game loop
            flags, game_complete = state[0], state[1][0]

            await self.location_check(ctx, flags)
            if game_complete & GAME_COMPLETE_MASK and not ctx.finished_game:
                await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                ctx.finished_game = True
            await self.received_items_check(ctx, flags)
            for name in CONSUMABLE_ITEMS:
                await self.consumable_check(ctx, name)
        except bizhawk.RequestFailedError:
            # The connector didn't respond. Exit handler and return to main loop to reconnect
            pass

    async def location_check(self, ctx: "BizHawkClientContext", flags: bytes) -> None:
        checked: list[int] = []
        for name, data in ctx.slot_data["locations"].items():
            location_id = LOCATION_NAME_TO_ID.get(name)
            if location_id is None or location_id not in ctx.missing_locations:
                continue
            offset = data["address"] - FLAGS_START
            if not 0 <= offset < FLAGS_SIZE:
                continue
            is_set = bool(flags[offset] & data["mask"])
            if is_set == bool(data["collected"]):
                checked.append(location_id)

        for location_id in await ctx.check_locations(checked):
            ctx.locations_checked.add(location_id)
            logger.info(f"New Check: {ctx.location_names.lookup_in_game(location_id)} "
                        f"({len(ctx.locations_checked)}/{len(ctx.missing_locations) + len(ctx.checked_locations)})")

    async def received_items_check(self, ctx: "BizHawkClientContext", flags: bytes) -> None:
        """Make the game's inventory match everything received. Every write is absolute, so it is safe to repeat
        after a reconnect or a save reload."""
        received: dict[str, int] = {}
        for network_item in ctx.items_received:
            name = ctx.item_names.lookup_in_game(network_item.item, ctx.game)
            received[name] = received.get(name, 0) + 1

        # Read what the game currently holds in every address we may write to
        addresses = sorted({data.address for name, data in ITEM_TABLE.items()
                            if name in received and data.address is not None}
                           | {CONTAINER_ITEMS[name][0] for name in CONTAINER_ITEMS if name in received})
        if not addresses:
            return
        current = {address: value[0] for address, value in zip(addresses, await bizhawk.read(
            ctx.bizhawk_ctx, [(address, 1, RAM) for address in addresses]))}
        desired = dict(current)

        for name, count in received.items():
            if name in CONTAINER_ITEMS:
                address, maximum = CONTAINER_ITEMS[name]
                start = ctx.slot_data["start_magic_containers" if name == "Magic Container"
                                      else "start_heart_containers"]
                desired[address] = max(desired[address], min(start + count, maximum))
                continue
            data = ITEM_TABLE[name]
            if data.address is None:
                continue  # filler, not delivered
            if data.mask == 0xFF:
                desired[data.address] = 1
            else:
                desired[data.address] |= data.mask

        writes = [(address, [value], RAM) for address, value in desired.items() if value != current[address]]
        if writes:
            await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, [(GAME_EVENT_ADDRESS, [GAME_EVENT_MAIN_LOOP], RAM)])

    async def consumable_check(self, ctx: "BizHawkClientContext", name: str) -> None:
        """Give one received copy of a consumable item per call, as long as the game can hold it."""
        address, maximum = CONSUMABLE_ITEMS[name]
        storage_key = f"z2r_given_{name.lower().replace(' ', '_')}_{ctx.team}_{ctx.slot}"
        ctx.set_notify(storage_key)
        if storage_key not in ctx.stored_data:
            return  # the server hasn't told us how many we've already given
        given = ctx.stored_data[storage_key] or 0

        received = sum(1 for item in ctx.items_received
                       if ctx.item_names.lookup_in_game(item.item, ctx.game) == name)
        if given >= received:
            return

        count = (await bizhawk.read(ctx.bizhawk_ctx, [(address, 1, RAM)]))[0][0]
        if count >= maximum:
            return  # wait until one is spent
        if not await bizhawk.guarded_write(
                ctx.bizhawk_ctx, [(address, [count + 1], RAM)],
                [(GAME_EVENT_ADDRESS, [GAME_EVENT_MAIN_LOOP], RAM), (address, [count], RAM)]):
            return

        ctx.stored_data[storage_key] = given + 1
        await ctx.send_msgs([{"cmd": "Set", "key": storage_key, "default": 0, "want_reply": False,
                              "operations": [{"operation": "add", "value": 1}]}])
