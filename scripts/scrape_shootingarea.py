#!/usr/bin/env python3
"""Scrape upcoming IPSC competitions from Shooting Area."""

import sys

from scraper_common import enrich_event_types, parse_table_events, run_scraper

SOURCE_URL = "https://www.shootingarea.eu/sk/calendar-ipsc"
BASE_URL = "https://www.shootingarea.eu/"


def parse_events(html, today):
    return parse_table_events(
        html,
        BASE_URL,
        today,
        date_column=0,
        location_column=2,
        link_column=6,
        row_classes={"tab_as", "tab_bs"},
        name_column=2,
    )


def parse_typed_events(html, today):
    return enrich_event_types(parse_events(html, today), "shootingarea")


if __name__ == "__main__":
    try:
        run_scraper(SOURCE_URL, "shootingarea", parse_typed_events)
    except Exception as error:
        print(f"Shooting Area scrape failed: {error}", file=sys.stderr)
        raise
