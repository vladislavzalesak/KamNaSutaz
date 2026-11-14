#!/usr/bin/env python3
"""Fetch upcoming LOS-SK competitions and write them to a CSV file."""

import csv
import re
import sys
import tempfile
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCE_URL = "https://los-sk.sk/index.php/competition/index"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "los-sk.csv"
DATE_PATTERN = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b")


class CompetitionTableParser(HTMLParser):
    """Extract event rows from the source page's competition table."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.table_found = False
        self.current_row = None
        self.current_cell = None
        self.events = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "cal2":
            self.in_table = True
            self.table_found = True
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in ("td", "th") and self.current_row is not None:
            self.current_cell = {"text": [], "links": []}
        elif self.current_cell is not None and tag == "a":
            href = attributes.get("href")
            if href:
                self.current_cell["links"].append(urljoin(SOURCE_URL, href))

    def handle_endtag(self, tag):
        if self.in_table and tag in ("td", "th") and self.current_cell is not None:
            text = " ".join("".join(self.current_cell["text"]).split())
            self.current_row.append((text, self.current_cell["links"]))
            self.current_cell = None
        elif self.in_table and tag == "tr" and self.current_row is not None:
            self._save_row()
            self.current_row = None
        elif tag == "table" and self.in_table:
            self.in_table = False

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell["text"].append(data)

    def _save_row(self):
        if len(self.current_row) < 3 or not any(cell[1] for cell in self.current_row):
            return

        date_match = DATE_PATTERN.search(self.current_row[1][0])
        if date_match is None:
            raise ValueError("Found a competition row without a DD.MM.YYYY date.")

        event_date = datetime.strptime(date_match.group(), "%d.%m.%Y").date()
        location = self.current_row[2][0]
        links = self.current_row[1][1]
        if not location or not links:
            raise ValueError("Found a competition row without a location or detail link.")

        self.events.append(
            {
                "date": event_date.isoformat(),
                "location": location,
                "url": links[0],
            }
        )


def parse_events(html, today):
    parser = CompetitionTableParser()
    parser.feed(html)
    if not parser.table_found:
        raise ValueError("The source page no longer contains the expected #cal2 table.")

    upcoming = [event for event in parser.events if event["date"] >= today.isoformat()]
    return sorted(upcoming, key=lambda event: event["date"])


def fetch_events():
    request = Request(
        SOURCE_URL,
        headers={"User-Agent": "KamNaSutaz event calendar scraper"},
    )
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")
    today = datetime.now(ZoneInfo("Europe/Bratislava")).date()
    return parse_events(html, today)


def write_events(events):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=OUTPUT_PATH.parent, delete=False
    ) as temporary_file:
        writer = csv.DictWriter(temporary_file, fieldnames=["date", "location", "url"])
        writer.writeheader()
        writer.writerows(events)
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(OUTPUT_PATH)


def main():
    events = fetch_events()
    write_events(events)
    print(f"Wrote {len(events)} upcoming LOS-SK competition(s) to {OUTPUT_PATH}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"LOS-SK scrape failed: {error}", file=sys.stderr)
        raise
