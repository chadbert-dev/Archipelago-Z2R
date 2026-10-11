import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from .. import Client
from ..Items import ITEM_NAME_TO_ID


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
    def run_check(self, received: list[str], ram: dict[int, int]) -> FakeRam:
        fake = FakeRam(ram)
        names = {ITEM_NAME_TO_ID[name]: name for name in received}
        ctx = SimpleNamespace(
            bizhawk_ctx=None, game="Z2R",
            items_received=[SimpleNamespace(item=ITEM_NAME_TO_ID[name]) for name in received],
            item_names=SimpleNamespace(lookup_in_game=lambda item, game: names[item]),
            slot_data={"start_magic_containers": 4, "start_heart_containers": 4,
                       "new_kasuto_basement_requirement": 8})
        client = Client.Z2RClient()
        with mock.patch.object(Client.bizhawk, "read", fake.read), \
                mock.patch.object(Client.bizhawk, "guarded_write", fake.guarded_write):
            asyncio.run(client.received_items_check(ctx, b""))
        return fake

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
