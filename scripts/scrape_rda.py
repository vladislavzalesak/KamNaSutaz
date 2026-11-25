#!/usr/bin/env python3
"""Scrape upcoming RDA IPSC matches."""

import sys
from html.parser import HTMLParser
from urllib.parse import urljoin

from scraper_common import make_event, parse_date, run_scraper, upcoming_events

SOURCE_URL = "https://match.rdaipsc.sk/"
SOURCE_ID = "rda"
BASE_URL = "https://match.rdaipsc.sk/"


class RdaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_depth = 0
        self.current = None
        self.row_depth = None
        self.events = []
        self.saw_event = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(attributes.get("class", "").split())
        if tag == "div":
            if self.current is None and "timeline-movement" in classes:
                self.current = {"text": [], "links": []}
                self.row_depth = self.div_depth
            self.div_depth += 1
        elif tag == "a" and self.current is not None:
            href = attributes.get("href")
            if href:
                self.current["links"].append(urljoin(BASE_URL, href))

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag != "div":
            return
        closing_depth = self.div_depth - 1
        if self.current is not None and closing_depth == self.row_depth:
            self._save_row()
            self.current = None
            self.row_depth = None
        self.div_depth -= 1

    def _save_row(self):
        text = " ".join("".join(self.current["text"]).split())
        event_date = parse_date(text)
        if event_date is None:
            return
        self.saw_event = True
        import re
        date_match = re.search(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", text)
        name = " ".join(text[date_match.end():].strip(" -").split()) if date_match else ""
        name = name or "RDA IPSC match"
        links = self.current["links"]
        self.events.append(
            make_event(
                event_date,
                "RDA IPSC",
                links[0] if links else "",
                name,
            )
        )


def parse_events(html, today):
    parser = RdaParser()
    parser.feed(html)
    if not parser.saw_event:
        raise ValueError("No RDA IPSC match dates found.")
    unique = {(event["date"], event["url"], event["name"]): event for event in parser.events}
    return upcoming_events(unique.values(), today)


def parse_typed_events(html, today):
    events = parse_events(html, today)
    for event in events:
        event["type"] = "IPSC"
    return events


if __name__ == "__main__":
    try:
        run_scraper(SOURCE_URL, SOURCE_ID, parse_typed_events)
    except Exception as error:
        print(f"RDA IPSC scrape failed: {error}", file=sys.stderr)
        raise
