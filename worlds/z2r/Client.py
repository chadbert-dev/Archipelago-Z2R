import logging
from typing import NamedTuple, TYPE_CHECKING

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


class Consumable(NamedTuple):
    address: int  # RAM address of the count
    maximum: int  # the most the client will raise the count to
    amount: int = 1  # added per item received
    scale_address: int | None = None  # if set, the amount is multiplied by the byte at this address
    size: int = 1  # bytes in the count, stored big endian (high byte at the lowest address)
    xp_table_index: int | None = None  # if set, the amount is the P-bag XP value for this bag size (0 = small)


# Items that are spent in game, so they are added one at a time instead of being set. The number already given is
# kept in the server's data storage so a reconnect doesn't give them again.
CONSUMABLE_ITEMS: dict[str, Consumable] = {
    "Small Key": Consumable(0x0793, 64),
    "1-Up": Consumable(0x0700, 99),
    # $070c is the magic the game still has to add to the player's magic, which it pays out over the next frames and
    # clamps to the maximum. The jar pickup routine at $E84B adds to it: 16 for a blue jar, 16 per magic container
    # for a red jar ($0783 is the number of magic containers).
    # $0755/$0756 (high, low) is the experience the game still has to award, like the magic buffer above.
    # P-bags give an amount from a 4 entry table in the ROM (one byte per bag size), which the Z2R app can shuffle.
    "Small P-Bag": Consumable(0x0755, 0xFFFF, size=2, xp_table_index=0),
    "Large P-Bag": Consumable(0x0755, 0xFFFF, size=2, xp_table_index=2),
    "Blue Magic Jar": Consumable(0x070C, 0xFF, 16),
    "Red Magic Jar": Consumable(0x070C, 0xFF, 16, scale_address=0x0783),
}
# CPU $E7F0 in the ROM's fixed bank: one byte per P-bag size, an index into XP_VALUES
PBAG_XP_TABLE_ADDRESS = 0x1E7F0  # in the "PRG ROM" domain
# The experience each table index stands for (XP_VALUES in the Z2R app's DropRandomizer.cs)
XP_VALUES = [0, 2, 3, 5, 10, 20, 30, 50, 70, 100, 150, 200, 300, 500, 700, 1000]
# The title screen hash: 6 characters at file offset 0x17C2C, each followed by a spacer tile (so 12 bytes). A tile is
# 0xD0 + a 5 bit value, with 0xD0-0xD9 being digits and 0xDA onwards letters.
HASH_ADDRESS = 0x17C1C  # in the "PRG ROM" domain
HASH_LENGTH = 6
# 1 while the main game loop is running. Item presence bits read as "collected" while the title screen is up,
# so nothing is read or written unless this is 1.
GAME_EVENT_ADDRESS = 0x076C
GAME_EVENT_MAIN_LOOP = 1


class Z2RClient(BizHawkClient):
    game = "Z2R"
    system = "NES"

    slot_name: str
    rom_seed: str
    rom_hash: str
    seed_mismatch_logged: bool

    def __init__(self) -> None:
        self.slot_name = ""
        self.rom_seed = ""
        self.rom_hash = ""
        self.seed_mismatch_logged = False

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        try:
            if await bizhawk.get_memory_size(ctx.bizhawk_ctx, "PRG ROM") < SIGNATURE_ADDRESS + SIGNATURE_SIZE:
                return False
            block, hash_tiles = await bizhawk.read(ctx.bizhawk_ctx, [
                (SIGNATURE_ADDRESS, SIGNATURE_SIZE, "PRG ROM"), (HASH_ADDRESS, HASH_LENGTH * 2, "PRG ROM")])
        except bizhawk.RequestFailedError:
            return False

        if block[:4] != SIGNATURE_MAGIC or block[4] != SIGNATURE_VERSION:
            return False

        self.slot_name = block[0x08:0x18].split(b"\x00")[0].decode("ascii", errors="replace")
        self.rom_seed = block[0x18:0x38].split(b"\x00")[0].decode("ascii", errors="replace")
        self.rom_hash = "".join(self.decode_hash_tile(hash_tiles[i * 2]) for i in range(HASH_LENGTH))
        self.seed_mismatch_logged = False
        ctx.game = self.game
        ctx.items_handling = 0b111
        ctx.want_slot_data = True
        return True

    @staticmethod
    def decode_hash_tile(tile: int) -> str:
        if 0xD0 <= tile <= 0xD9:
            return chr(tile - 0xA0)
        if 0xDA <= tile <= 0xF3:
            return chr(tile - 0x99)
        return "?"

    async def set_auth(self, ctx: "BizHawkClientContext") -> None:
        ctx.auth = self.slot_name

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        if ctx.server is None or ctx.server.socket.closed or ctx.slot_data is None:
            return

        # The signature holds the first 32 characters of the seed, with non-ASCII characters replaced by "?"
        expected_seed = "".join(c if " " <= c <= "~" else "?" for c in ctx.slot_data.get("rom_seed", ""))[:32]
        expected_hash = ctx.slot_data.get("rom_hash", "")
        if (expected_seed and expected_seed != self.rom_seed) or (expected_hash and expected_hash != self.rom_hash):
            if not self.seed_mismatch_logged:
                logger.error(f"This ROM is seed '{self.rom_seed}' with hash '{self.rom_hash}', but the multiworld "
                             f"expects seed '{expected_seed}' with hash '{expected_hash}'. Open the ROM that "
                             f"matches your YAML.")
                self.seed_mismatch_logged = True
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
        consumable = CONSUMABLE_ITEMS[name]
        address = consumable.address
        storage_key = f"z2r_given_{name.lower().replace(' ', '_')}_{ctx.team}_{ctx.slot}"
        ctx.set_notify(storage_key)
        if storage_key not in ctx.stored_data:
            return  # the server hasn't told us how many we've already given
        given = ctx.stored_data[storage_key] or 0

        received = sum(1 for item in ctx.items_received
                       if ctx.item_names.lookup_in_game(item.item, ctx.game) == name)
        if given >= received:
            return

        reads = [(address, consumable.size, RAM)]
        if consumable.scale_address is not None:
            reads.append((consumable.scale_address, 1, RAM))
        if consumable.xp_table_index is not None:
            reads.append((PBAG_XP_TABLE_ADDRESS + consumable.xp_table_index, 1, "PRG ROM"))
        values = await bizhawk.read(ctx.bizhawk_ctx, reads)
        count_bytes = values[0]
        count = int.from_bytes(count_bytes, "big")
        amount = consumable.amount
        if consumable.scale_address is not None:
            amount *= values[1][0]
        if consumable.xp_table_index is not None:
            amount = XP_VALUES[values[-1][0] & 0x0F]
        if amount and count + amount > consumable.maximum:
            return  # wait until some is spent
        if amount:  # an amount of 0 (e.g. a 0 XP bag) has nothing to write but still counts as given
            new_bytes = list((count + amount).to_bytes(consumable.size, "big"))
            if not await bizhawk.guarded_write(
                    ctx.bizhawk_ctx, [(address, new_bytes, RAM)],
                    [(GAME_EVENT_ADDRESS, [GAME_EVENT_MAIN_LOOP], RAM), (address, list(count_bytes), RAM)]):
                return

        ctx.stored_data[storage_key] = given + 1
        await ctx.send_msgs([{"cmd": "Set", "key": storage_key, "default": 0, "want_reply": False,
                              "operations": [{"operation": "add", "value": 1}]}])
