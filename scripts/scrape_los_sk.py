#!/usr/bin/env python3
"""Scrape upcoming competitions from LOS-SK."""

import sys

from scraper_common import enrich_event_types, parse_table_events, run_scraper

SOURCE_URL = "https://los-sk.sk/index.php/competition/index"
SOURCE_ID = "los-sk"


def parse_events(html, today):
    return parse_table_events(
        html,
        SOURCE_URL,
        today,
        date_column=1,
        location_column=2,
        link_column=1,
        name_column=0,
    )


def parse_typed_events(html, today):
    return enrich_event_types(parse_events(html, today), SOURCE_ID)


if __name__ == "__main__":
    try:
        run_scraper(SOURCE_URL, SOURCE_ID, parse_typed_events)
    except Exception as error:
        print(f"LOS-SK scrape failed: {error}", file=sys.stderr)
        raise
