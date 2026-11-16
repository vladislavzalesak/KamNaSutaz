"""Validate, write, and restore duplicate grouping thresholds."""

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "duplicate-thresholds.json"


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Duplicate thresholds must be a JSON object.")

    possible = config.get("possible_threshold")
    strict = config.get("strict_threshold")
    values = (possible, strict)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or value > 1
        for value in values
    ):
        raise ValueError("Duplicate thresholds must be numbers between 0 and 1.")
    if strict < possible:
        raise ValueError("The strict threshold must be at least the possible threshold.")
    return config


def write_config(possible_percent, strict_percent, path=CONFIG_PATH):
    possible = float(possible_percent)
    strict = float(strict_percent)
    if any(
        not math.isfinite(value) or value < 0 or value > 100
        for value in (possible, strict)
    ):
        raise ValueError("Threshold inputs must be percentages between 0 and 100.")

    config = {
        "possible_threshold": possible / 100,
        "strict_threshold": strict / 100,
    }
    validate_config(config)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("possible_threshold", type=float)
    parser.add_argument("strict_threshold", type=float)
    arguments = parser.parse_args()
    try:
        write_config(arguments.possible_threshold, arguments.strict_threshold)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
