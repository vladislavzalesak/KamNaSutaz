#!/usr/bin/env python3
"""Scrape upcoming competitions from SADS."""

import sys

from scraper_common import parse_table_events, run_scraper

SOURCE_URL = (
    "https://new.sads.sk/index.php?option=com_kalendar&view=preteky&Itemid=414"
)


def parse_events(html, today):
    return parse_table_events(
        html,
        SOURCE_URL,
        today,
        date_column=2,
        location_column=6,
        link_column=3,
    )


if __name__ == "__main__":
    try:
        run_scraper(SOURCE_URL, "sads", parse_events)
    except Exception as error:
        print(f"SADS scrape failed: {error}", file=sys.stderr)
        raise
