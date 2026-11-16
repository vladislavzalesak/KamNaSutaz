#!/usr/bin/env python3
"""Scrape upcoming competitions from SADS."""

import sys
from urllib.parse import parse_qs, urlsplit

from scraper_common import (
    TableEventParser,
    enrich_event_types,
    fetch_html,
    run_scraper,
    upcoming_events,
)

SOURCE_URL = (
    "https://new.sads.sk/index.php?option=com_kalendar&view=preteky&Itemid=414"
)
MAX_PAGES = 100


def pagination_offset(url):
    parsed_url = urlsplit(url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc.lower() not in {"new.sads.sk", "sads.sk"}
    ):
        return None
    query = parse_qs(parsed_url.query)
    if query.get("option") != ["com_kalendar"] or query.get("view") != ["preteky"]:
        return None
    value = query.get("limitstart", ["0"])[0]
    if not value.isdigit():
        return None
    return int(value)


def parse_events(html, today):
    pending_urls = [SOURCE_URL]
    visited_offsets = set()
    events = {}

    while pending_urls:
        page_url = pending_urls.pop(0)
        offset = pagination_offset(page_url)
        if offset is None or offset in visited_offsets:
            continue
        if len(visited_offsets) >= MAX_PAGES:
            raise ValueError(f"SADS calendar exceeded the {MAX_PAGES}-page limit.")
        visited_offsets.add(offset)

        page_html = html if page_url == SOURCE_URL else fetch_html(page_url)
        parser = TableEventParser(
            SOURCE_URL,
            date_column=2,
            location_column=6,
            link_column=3,
            name_column=3,
        )
        parser.feed(page_html)
        if not parser.saw_calendar_row:
            raise ValueError(f"No SADS competition rows found on page {offset}.")

        for event in parser.events:
            events[(event["date"], event["url"])] = event
        for link in parser.links:
            if pagination_offset(link) is not None:
                pending_urls.append(link)

    return upcoming_events(events.values(), today)


def parse_typed_events(html, today):
    return enrich_event_types(parse_events(html, today), "sads")


if __name__ == "__main__":
    try:
        run_scraper(SOURCE_URL, "sads", parse_typed_events)
    except Exception as error:
        print(f"SADS scrape failed: {error}", file=sys.stderr)
        raise
