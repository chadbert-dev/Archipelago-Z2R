# Z2R Multiworld Setup Guide

## Required software

- [BizHawk](https://tasvideos.org/BizHawk) 2.7 or later
- The Archipelago client, from the Archipelago installer
- The Z2R app, with Archipelago mode enabled

## Setup

1. In the Z2R app, enable Archipelago mode, enter your slot name (up to 16 characters) and generate a seed. The app
   writes the ROM along with `_requirements.json` and `_ap_locations.json` files.
2. The app also writes a player YAML. Its `name` must match the slot name in the ROM, and its `rom_seed` and `hash` must match
   the seed and title screen hash of the ROM, or the client will refuse the ROM.
3. Generate the multiworld and host it.

## Connecting

1. Open the generated ROM in BizHawk (Zelda II is an NES game).
2. Open the Archipelago Launcher and choose "BizHawk Client".
3. In BizHawk, open Tools > Lua Console and load `data/lua/connector_bizhawk_generic.lua`, or let the launcher start
   BizHawk for you.
4. Connect the client to the server address. The slot name is read from the ROM, so no name needs to be typed.

## Notes

- The Great Palace, Thunderbird and Dark Link need `crystals_required` crystals (one per palace boss, up to 6).
- Set `replace_fire_with_dash: true` only if the seed was generated with Dash replacing Fire. Otherwise logic that
  needs Dash uses the Fairy spell.
- Defeating Thunderbird requires the Thunder spell, which is hardcoded because the Z2R app's requirements output
  doesn't include it.
