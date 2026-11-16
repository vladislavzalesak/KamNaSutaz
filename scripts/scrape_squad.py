#!/usr/bin/env python3
"""Scrape upcoming competitions from SQUAD."""

import sys
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin
from scraper_common import (
    enrich_event_types,
    make_event,
    parse_date,
    run_scraper,
    upcoming_events,
)

SOURCE_URL = "https://squad.sk/"


class SquadParser(HTMLParser):
    """Extract event cards from SQUAD's div-based calendar."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_depth = 0
        self.event_depth = None
        self.field_depth = None
        self.field = None
        self.current = None
        self.events = []
        self.saw_event = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(attributes.get("class", "").split())

        if tag == "div":
            if self.current is None and "zavod" in classes:
                self.current = {
                    "datum": [],
                    "name": [],
                    "misto": [],
                    "links": [],
                }
                self.event_depth = self.div_depth
            elif self.current is not None:
                field = next(
                    (
                        name
                        for name in ("datum", "name", "misto")
                        if name in classes
                    ),
                    None,
                )
                if field:
                    self.field = field
                    self.field_depth = self.div_depth
                    self.current[field].append([])
            self.div_depth += 1
        elif tag == "br" and self.current is not None and self.field:
            self.current[self.field][-1].append(" ")
        elif tag == "a" and self.current is not None:
            href = attributes.get("href")
            if href:
                self.current["links"].append(urljoin(SOURCE_URL, href))

    def handle_data(self, data):
        if self.current is not None and self.field:
            self.current[self.field][-1].append(data)

    def handle_endtag(self, tag):
        if tag != "div":
            return

        closing_depth = self.div_depth - 1
        if self.current is not None and closing_depth == self.event_depth:
            self._save_event()
            self.current = None
            self.event_depth = None
            self.field = None
            self.field_depth = None
        elif self.current is not None and closing_depth == self.field_depth:
            self.field = None
            self.field_depth = None
        self.div_depth -= 1

    def _save_event(self):
        date_text = "".join("".join(part) for part in self.current["datum"])
        event_date = parse_date(date_text)
        if event_date is None:
            return
        self.saw_event = True
        location = next(
            (
                " ".join("".join(part).split())
                for part in reversed(self.current["misto"])
                if "".join(part).strip()
            ),
            "",
        )
        name = next(
            (
                " ".join("".join(part).split())
                for part in self.current["name"]
                if "".join(part).strip()
            ),
            "",
        )
        self.events.append(
            make_event(
                event_date,
                location,
                self.current["links"][0] if self.current["links"] else "",
                name,
            )
        )


def parse_events(html, today: date):
    parser = SquadParser()
    parser.feed(html)
    if not parser.saw_event:
        raise ValueError("No SQUAD event cards found.")
    return upcoming_events(parser.events, today)


def parse_typed_events(html, today):
    return enrich_event_types(parse_events(html, today), "squad")


if __name__ == "__main__":
    try:
        run_scraper(SOURCE_URL, "squad", parse_typed_events)
    except Exception as error:
        print(f"SQUAD scrape failed: {error}", file=sys.stderr)
        raise
