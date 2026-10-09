"""Turns the Z2R app's output files into the options a Z2R player YAML needs.

    python -m worlds.z2r.convert <seed>_requirements.json <seed>_ap_locations.json [starting items...]
"""
import json
import sys
from typing import Any


def build_options(requirements: dict[str, Any], ap_locations: dict[str, Any]) -> dict[str, Any]:
    return {
        "locations": {
            location["nodeId"]: {
                "address": location["address"],
                "mask": location["mask"],
                "collected": location["collectedBitValue"],
            } for location in ap_locations["locations"]
        },
        "rules": {
            target["target"]: [route["requirements"] for route in target["routes"]]
            for target in requirements["targets"]
        },
    }


def main() -> None:
    with open(sys.argv[1]) as f:
        requirements = json.load(f)
    with open(sys.argv[2]) as f:
        ap_locations = json.load(f)
    # JSON is valid YAML, so the options can be pasted under "Zelda II: Z2R:" in the player YAML
    print(json.dumps(build_options(requirements, ap_locations), indent=2))


if __name__ == "__main__":
    main()
