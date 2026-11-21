"""Real item sprites for this slot's own items.

Z2R draws every AP item with one 8x16 sprite. Older builds use the 1-up's tiles for it, which the Z2R app replaces
with half of the Archipelago logo; the newest build uses its own tile (FIXED_LEFT_ADDRESS) and keeps the 1-up's. The ROM is built before the multiworld exists, so it can't know what each location holds. The client
does: when Link is in a side view room whose item is one of this slot's own Z2R items, it copies that item's tiles over
the AP tiles in every CHR bank, and puts the logo back in any other room.

Which room holds which location comes from the item presence flags in slot data: the game keeps one bit per item, at
table base + map / 2, with the bit picked by the map's parity and the item's page (ApManifestBuilder in the app).
"""
from typing import NamedTuple

CHR_DOMAIN = "CHR VROM"
BANK_SIZE = 0x2000
AP_TILE_OFFSET = 0x0A80  # the 1-up's tiles in each 8 KB CHR bank (CHR.ONEUP is 0x8A80, in bank 4)
REFERENCE_BANK = 4
TILE_BYTES = 32  # an 8x16 sprite: the top 8x8 tile, then the bottom one
# Half of the Archipelago logo as the Z2R app draws it (ArchipelagoLogo.Logo), for when the ROM's copy was overwritten
AP_LOGO = bytes.fromhex("0002007dfdffc6380307037dfcfec60054b4ab27570707032848535727070703")
# The 1-up's own tiles from the vanilla ROM (bank 4, 0xA80). Z2R's seed ROM has the logo there, so a 1-Up can't be copied
# from the ROM the way other items are.
ONE_UP_TILES = bytes.fromhex("556086468659865d9a010d5b1b5a55308647866a865d9b0376c1037681037999")
# Newer Z2R builds draw the AP item 16 pixels wide: a second 8x16 sprite, tile $C7, holds the logo's right half. Its
# tiles are at CHR 0x1A060, in the item sprite page that every room maps, so there is one copy. Older ROMs leave it blank.
# The game draws that second sprite flipped horizontally, so its tiles are stored mirrored (ArchipelagoLogo.LogoRight).
RIGHT_TILE_ADDRESS = 0x1A060
AP_LOGO_RIGHT = bytes.fromhex("00020201000100380307037d7dffc6387cdcfb77670707037cfcfb7777070703")
BLANK = bytes(TILE_BYTES)
# Newest Z2R builds draw the AP item as tiles $FD (left) and $C7 (right) and leave the 1-up's tiles alone. The left half
# is at CHR 0x1A3C0 (tiles $FC/$FD of the item sprite page), blank in older ROMs.
FIXED_LEFT_ADDRESS = 0x1A3C0

# Palettes. Items $10 and up take their sprite palette from ItemPaletteTable (FullItemShuffle.s in the app), which
# the code at $F120 in bank 7 reads with "lda ItemPaletteTable - $10,x". The AP item is item $26 there, with palette 3
# (the blue jar's). Items below $10 (the hammer, candle and so on) use palette 1.
PRG_DOMAIN = "PRG ROM"
PALETTE_LOAD = 0x1F120  # PRG ROM offset of that lda: $BD, then the table's address - $10
AP_ITEM_ID = 0x26
# One stable logo color for every AP item (palette 1, the one most items use), so the logo never changes by area.
AP_PALETTE = 1
AP_PROGRESSION_PALETTE = 1  # same color: progression items are not marked red
ITEM_PALETTES = {"Blue Magic Jar": 3, "Red Magic Jar": 2, "1-Up": 0}  # every other item: 1


def item_palette(name: str) -> int:
    return ITEM_PALETTES.get(name, 1)


def palette_address(load: bytes) -> int | None:
    """PRG ROM offset of the AP item's palette byte, from the 3 bytes at PALETTE_LOAD, or None if they aren't the
    expected lda (a ROM from an older app build)."""
    if len(load) < 3 or load[0] != 0xBD:
        return None
    cpu = (load[1] | load[2] << 8) + AP_ITEM_ID
    if not 0xE000 <= cpu <= 0xFFFF:
        return None
    return PALETTE_LOAD - 0x3120 + (cpu - 0xC000)

# RAM (ram.inc in the Z2R app)
MAP_NUMBER = 0x0561
REGION_NUMBER = 0x0706  # 0 west, 1 Death Mountain, 2 east, 3 Maze Island
WORLD_NUMBER = 0x0707  # 0 caves, 1 west towns, 2 east towns, 3 palaces 1/2/5, 4 palaces 3/4/6, 5 Great Palace
LINK_PAGE = 0x003B  # which page of the room Link is in

CAVE_TABLES = {0: 0x0600, 1: 0x0620, 2: 0x0640, 3: 0x0620}
WORLD_TABLES = {1: 0x0660, 2: 0x0660, 3: 0x0680, 4: 0x06A0}


class Tile(NamedTuple):
    address: int  # CHR address of an 8x16 tile pair (CHR.cs in the app)
    x: int = 0  # 0 left, 1 right half of the 16 pixel wide item
    flip: bool = False  # drawn mirrored


# How the game draws each item (CHR.COLLECTABLE_TILES in the app). One tile is 8 pixels wide like the AP item; a
# 16 pixel item is squeezed to 8.
ITEM_TILES: dict[str, list[Tile]] = {
    "Candle": [Tile(0x88C0)],
    "Glove": [Tile(0x88E0)],
    "Raft": [Tile(0x8900)],
    "Boots": [Tile(0x8920)],
    "Flute": [Tile(0x8940)],
    "Cross": [Tile(0x8960)],
    "Hammer": [Tile(0x8980)],
    "Magic Key": [Tile(0x89A0)],
    "Small Key": [Tile(0x8660)],
    "Small P-Bag": [Tile(0x8720)],
    "Large P-Bag": [Tile(0x8720)],
    "Blue Magic Jar": [Tile(0x88A0)],
    "Red Magic Jar": [Tile(0x88A0)],
    "Magic Container": [Tile(0x1820), Tile(0x1820, 1, True)],
    "Heart Container": [Tile(0x1800), Tile(0x1800, 1, True)],
    "Trophy": [Tile(0x32E0), Tile(0x32E0, 1, True)],
    "Medicine": [Tile(0x3300), Tile(0x3300, 1, True)],
    "Child": [Tile(0x5300), Tile(0x5300, 1, True)],
    "Mirror": [Tile(0x1A260)],
    "Bagu's Note": [Tile(0x1A280)],
    "Water": [Tile(0x1A2C0)],
    "Upstab": [Tile(0x1A200)],
    "Downstab": [Tile(0x1A220)],
    "Shield Spell": [Tile(0x1A3A0), Tile(0x1A3A0, 1, True)],
    "Jump Spell": [Tile(0x1A140), Tile(0x1A120, 1)],
    "Life Spell": [Tile(0x1A160), Tile(0x1A180, 1, True)],
    "Fairy Spell": [Tile(0x86A0)],
    "Fire Spell": [Tile(0x1A0E0), Tile(0x1A100, 1)],
    "Reflect Spell": [Tile(0x1A1A0), Tile(0x1A1C0, 1, True)],
    "Spell Spell": [Tile(0x1A300), Tile(0x1A300, 1, True)],
    "Thunder Spell": [Tile(0x1A360), Tile(0x1A380, 1, True)],
    "Dash Spell": [Tile(0x1A0E0), Tile(0x1A140, 1)],
}

SOURCE_ADDRESSES = sorted({tile.address for tiles in ITEM_TILES.values() for tile in tiles})


def decode(data: bytes) -> list[list[int]]:
    """An 8x16 tile pair as 16 rows of 8 pixel values (0-3)."""
    rows = []
    for half in (0, 16):
        for y in range(8):
            low, high = data[half + y], data[half + 8 + y]
            rows.append([((low >> (7 - x)) & 1) | (((high >> (7 - x)) & 1) << 1) for x in range(8)])
    return rows


def encode(rows: list[list[int]]) -> bytes:
    """16 rows of 8 pixel values back into an 8x16 tile pair."""
    out = bytearray(TILE_BYTES)
    for y, row in enumerate(rows):
        half, line = (0, y) if y < 8 else (16, y - 8)
        for x, value in enumerate(row):
            out[half + line] |= (value & 1) << (7 - x)
            out[half + 8 + line] |= (value >> 1) << (7 - x)
    return bytes(out)


def item_sprite(name: str, sources: dict[int, bytes]) -> bytes | None:
    """The AP tiles drawn as this Z2R item, from the ROM's own tiles (so custom item sprites carry over), or None if it
    isn't a Z2R item with a sprite. A 16 pixel wide item is squeezed to 8, keeping a drawn pixel of each pair."""
    if name == "1-Up":
        return ONE_UP_TILES
    tiles = ITEM_TILES.get(name)
    if not tiles or any(tile.address not in sources for tile in tiles):
        return None
    if len(tiles) == 1 and not tiles[0].flip:
        return bytes(sources[tiles[0].address])
    if len(tiles) == 2 and tiles[0] == Tile(tiles[1].address) and tiles[1] == Tile(tiles[0].address, 1, True):
        # A mirrored item (left half, then the same half flipped): squeeze the half to 4 pixels, keeping the
        # strongest color of each pair so the outline survives, and mirror it, so both sides match
        half = [[max(row[2 * x], row[2 * x + 1]) for x in range(4)] for row in decode(sources[tiles[0].address])]
        return encode([row + row[::-1] for row in half])
    wide = full_width(tiles, sources)
    return encode([[row[2 * x] or row[2 * x + 1] for x in range(8)] for row in wide])


def full_width(tiles: list[Tile], sources: dict[int, bytes]) -> list[list[int]]:
    """16 rows of 16 pixel values: the item as the game draws it."""
    wide = [[0] * 16 for _ in range(16)]
    for tile in tiles:
        for y, row in enumerate(decode(sources[tile.address])):
            for x, value in enumerate(reversed(row) if tile.flip else row):
                wide[y][tile.x * 8 + x] = value
    return wide


def wide_item_sprite(name: str, sources: dict[int, bytes]) -> bytes | None:
    """Both AP sprites drawn as this Z2R item, for a ROM with the 16 pixel AP item: the left tiles, then the right
    ones (RIGHT_TILE_ADDRESS), 64 bytes. The game flips the right sprite, so its tiles are stored mirrored. An 8 pixel
    item gets a blank right half, as the game draws it. None if it isn't a Z2R item with a sprite."""
    if name == "1-Up":
        return ONE_UP_TILES + BLANK
    tiles = ITEM_TILES.get(name)
    if not tiles or any(tile.address not in sources for tile in tiles):
        return None
    wide = full_width(tiles, sources)
    return encode([row[:8] for row in wide]) + encode([row[15:7:-1] for row in wide])


def flag_table(world: int, region: int) -> int | None:
    """The item presence table of the side view Link is in, or None where items are never AP items."""
    if world == 0:
        return CAVE_TABLES.get(region)
    return WORLD_TABLES.get(world)


def page_mask(map_number: int, page: int) -> int:
    return (0x80 if map_number % 2 == 0 else 0x08) >> page


def room_locations(locations: dict[str, dict], world: int, region: int, map_number: int, link_page: int) -> list[str]:
    """Names of the item presence locations in this room, the one nearest Link's page first."""
    table = flag_table(world, region)
    if table is None:
        return []
    address = table + (map_number >> 1)
    found = []
    for name, data in locations.items():
        if data.get("address") != address or data.get("collected", 1) != 0:
            continue
        for page in range(4):
            if data.get("mask") == page_mask(map_number, page):
                found.append((abs(page - link_page), page, name))
    return [name for _distance, _page, name in sorted(found)]
