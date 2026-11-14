#!/usr/bin/env python3
"""Scrape upcoming IPSC competitions from Shooting Area."""

import sys

from scraper_common import parse_table_events, run_scraper

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
    )


if __name__ == "__main__":
    try:
        run_scraper(SOURCE_URL, "shootingarea", parse_events)
    except Exception as error:
        print(f"Shooting Area scrape failed: {error}", file=sys.stderr)
        raise
