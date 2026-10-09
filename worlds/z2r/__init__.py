from collections.abc import Callable
from typing import Any

from BaseClasses import CollectionState, Item, ItemClassification, Region, Tutorial
from worlds.AutoWorld import WebWorld, World
from .Items import (CONTAINER_ITEMS, CONTAINER_REQUIREMENTS, FILLER_ITEMS, ITEM_NAME_TO_ID, ITEM_TABLE, POOL_PRIORITY,
                    REQUIREMENT_ITEMS, Z2RItem)
from .Locations import (CRYSTAL_ITEM, CRYSTALS_REQUIRED, GOAL_EVENT, GOAL_NODE, LOCATION_NAME_TO_ID, PALACE_BOSS_NODES,
                        Z2RLocation)
from .Options import Z2ROptions
from .Client import Z2RClient  # required to register the client with the BizHawk client


class Z2RWeb(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to playing Zelda II: Z2R in an Archipelago multiworld.",
        "English",
        "multiworld_en.md",
        "multiworld/en",
        ["Chad Hansen"]
    )]


class Z2RWorld(World):
    """
    Zelda II: The Adventure of Link is the second game in The Legend of Zelda series. Z2R is a randomizer for it
    that shuffles items, palaces, towns and the overworld. In this multiworld mode the Z2R app generates the seed
    logic and the ROM, and Archipelago decides what every major item location gives.
    """
    game = "Zelda II: Z2R"
    web = Z2RWeb()
    options_dataclass = Z2ROptions
    options: Z2ROptions
    topology_present = False

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID

    @classmethod
    def stage_assert_generate(cls, multiworld) -> None:
        for player in multiworld.get_game_players(cls.game):
            options = multiworld.worlds[player].options
            name = multiworld.get_player_name(player)
            if not options.locations.value or not options.rules.value:
                raise Exception(f"Z2R settings submitted without locations or rules ({name}). "
                                f"Generate the YAML with the Z2R app in Archipelago mode.")
            unknown = [loc for loc in options.locations.value if loc not in LOCATION_NAME_TO_ID]
            if unknown:
                raise Exception(f"Z2R locations unknown to this version of the world ({name}): {', '.join(unknown)}")
            required = [*options.locations.value, GOAL_NODE, *PALACE_BOSS_NODES]
            missing = [loc for loc in required if loc not in options.rules.value]
            if missing:
                raise Exception(f"Z2R rules for {name} have no entry for: {', '.join(missing)}")

    def _rule_for(self, routes: list[list[str]]) -> Callable[[CollectionState], bool]:
        """Routes are alternatives (OR) of requirement lists (AND)."""
        player = self.player
        start_magic = self.options.start_magic_containers.value
        parsed: list[list[tuple[str, int]]] = []
        for route in routes:
            requirements: list[tuple[str, int]] = []
            for token in route:
                if token == "DASH" and not self.options.replace_fire_with_dash:
                    requirements.append(("Fairy Spell", 1))  # no Dash in this seed, so logic falls back to Fairy
                elif token in REQUIREMENT_ITEMS:
                    requirements.append((REQUIREMENT_ITEMS[token], 1))
                elif token in CONTAINER_REQUIREMENTS:
                    # The count includes the containers the ROM starts with
                    requirements.append(("Magic Container", max(CONTAINER_REQUIREMENTS[token] - start_magic, 0)))
                else:
                    raise Exception(f"Unknown Z2R requirement '{token}' for {self.player_name}")
            parsed.append(requirements)

        def rule(state: CollectionState) -> bool:
            return any(all(state.has(item, player, count) for item, count in route) for route in parsed)

        return rule

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        rules = self.options.rules.value
        for name in self.options.locations.value:
            location = Z2RLocation(self.player, name, LOCATION_NAME_TO_ID[name], menu)
            # stage_assert_generate rejects real seeds with missing rules; defaults keep the generic tests working
            location.access_rule = self._rule_for(rules.get(name, [[]]))
            menu.locations.append(location)

        for i, node in enumerate(PALACE_BOSS_NODES):
            boss = Z2RLocation(self.player, f"Defeat Palace Boss {i + 1}", None, menu)
            boss.access_rule = self._rule_for(rules.get(node, [[]]))
            boss.place_locked_item(Z2RItem(CRYSTAL_ITEM, ItemClassification.progression, None, self.player))
            menu.locations.append(boss)

        goal = Z2RLocation(self.player, GOAL_EVENT, None, menu)
        great_palace = self._rule_for(rules.get(GOAL_NODE, [[]]))
        player = self.player
        # Thunderbird, the Great Palace boss, can only be hurt with the Thunder spell. The Z2R app's routes
        # don't include it, so it is hardcoded here.
        goal.access_rule = lambda state: (state.has(CRYSTAL_ITEM, player, CRYSTALS_REQUIRED)
                                          and state.has("Thunder Spell", player) and great_palace(state))
        goal.place_locked_item(Z2RItem(GOAL_EVENT, ItemClassification.progression, None, self.player))
        menu.locations.append(goal)
        self.multiworld.regions.append(menu)

    def set_rules(self) -> None:
        self.multiworld.completion_condition[self.player] = lambda state: state.has(GOAL_EVENT, self.player)

    def create_item(self, name: str) -> Item:
        return Z2RItem(name, ITEM_TABLE[name].classification, ITEM_NAME_TO_ID[name], self.player)

    def create_items(self) -> None:
        starting = {name: int(count) for name, count in self.options.starting_items.value.items()}
        for name, count in starting.items():
            if name not in ITEM_TABLE or name in CONTAINER_ITEMS:
                raise Exception(f"Unknown Z2R starting item '{name}' for {self.player_name}")
            for _ in range(count):
                self.multiworld.push_precollected(self.create_item(name))

        uses_dash = bool(self.options.replace_fire_with_dash)
        candidates: list[str] = []
        for name in POOL_PRIORITY:
            if name in CONTAINER_ITEMS:
                start = (self.options.start_magic_containers if name == "Magic Container"
                         else self.options.start_heart_containers).value
                candidates += [name] * (CONTAINER_ITEMS[name][1] - start)
            elif name == "Dash Spell" and not uses_dash:
                continue
            elif name == "Fire Spell" and uses_dash:
                continue
            elif name not in starting:
                candidates.append(name)

        slots = len(self.options.locations.value)
        pool = candidates[:slots]
        filler_count = slots - len(pool)
        pool += [self.get_filler_item_name() for _ in range(filler_count)]
        self.multiworld.itempool += [self.create_item(name) for name in pool]

    def get_filler_item_name(self) -> str:
        return self.random.choice(FILLER_ITEMS)

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "locations": {name: dict(data) for name, data in self.options.locations.value.items()},
            "start_magic_containers": self.options.start_magic_containers.value,
            "start_heart_containers": self.options.start_heart_containers.value,
            "replace_fire_with_dash": bool(self.options.replace_fire_with_dash),
        }
