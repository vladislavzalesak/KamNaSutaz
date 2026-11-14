"""Shared helpers for the independent event calendar scrapers."""

import csv
import json
import re
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

DATE_PATTERN = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b")
ROOT = Path(__file__).resolve().parents[1]


def parse_date(value):
    match = DATE_PATTERN.search(value)
    if match is None:
        return None
    return datetime.strptime(match.group(), "%d.%m.%Y").date()


def make_event(event_date, location, url):
    if not location or not url:
        raise ValueError("Found a competition row without a location or detail link.")
    return {
        "date": event_date.isoformat(),
        "location": " ".join(location.split()),
        "url": url,
    }


def upcoming_events(events, today):
    return sorted(
        (event for event in events if event["date"] >= today.isoformat()),
        key=lambda event: event["date"],
    )


class TableEventParser(HTMLParser):
    """Extract date, venue, and detail link from calendar table rows."""

    def __init__(
        self,
        base_url,
        date_column,
        location_column,
        link_column,
        row_classes=None,
    ):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.date_column = date_column
        self.location_column = location_column
        self.link_column = link_column
        self.row_classes = row_classes
        self.row = None
        self.cell = None
        self.saw_calendar_row = False
        self.events = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "tr":
            self.row = {"class": attributes.get("class", ""), "cells": []}
        elif tag in ("td", "th") and self.row is not None:
            self.cell = {"text": [], "links": []}
        elif tag == "br" and self.cell is not None:
            self.cell["text"].append("\n")
        elif tag == "a":
            href = attributes.get("href")
            if href:
                link = urljoin(self.base_url, href)
                self.links.append(link)
                if self.cell is not None:
                    self.cell["links"].append(link)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row["cells"].append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self._save_row()
            self.row = None

    def _save_row(self):
        if self.row_classes is not None and not (
            set(self.row["class"].split()) & self.row_classes
        ):
            return

        cells = self.row["cells"]
        required_column = max(
            self.date_column, self.location_column, self.link_column
        )
        if len(cells) <= required_column:
            return

        event_date = parse_date(" ".join(cells[self.date_column]["text"]))
        if event_date is None:
            return
        self.saw_calendar_row = True

        location_text = "".join(cells[self.location_column]["text"])
        location_lines = [
            line.strip() for line in location_text.splitlines() if line.strip()
        ]
        location = location_lines[-1] if location_lines else ""
        links = cells[self.link_column]["links"]
        self.events.append(make_event(event_date, location, links[0] if links else ""))


def parse_table_events(
    html,
    base_url,
    today,
    date_column,
    location_column,
    link_column,
    row_classes=None,
):
    parser = TableEventParser(
        base_url,
        date_column,
        location_column,
        link_column,
        row_classes,
    )
    parser.feed(html)
    if not parser.saw_calendar_row:
        raise ValueError(f"No competition rows found at {base_url}.")
    return upcoming_events(parser.events, today)


def fetch_html(url):
    import ssl

    import certifi

    request = Request(url, headers={"User-Agent": "KamNaSutaz event calendar scraper"})
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    with urlopen(request, timeout=30, context=context) as response:
        return response.read().decode("utf-8")


def run_scraper(url, source_id, parse_events):
    metadata_path = ROOT / "data" / f"{source_id}.json"
    previous_metadata = read_metadata(metadata_path, source_id)
    csv_path = None

    try:
        today = datetime.now(ZoneInfo("Europe/Bratislava")).date()
        events = parse_events(fetch_html(url), today)
        scraped_at = datetime.now(timezone.utc)
        filename = f"{source_id}_{scraped_at.strftime('%Y%m%dT%H%M%S%fZ')}.csv"
        csv_path = ROOT / "data" / filename
        write_events(csv_path, events)

        completed_at = datetime.now(timezone.utc)
        timestamp = completed_at.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        write_metadata(
            metadata_path,
            {
                "source_id": source_id,
                "file": filename,
                "last_successful_at": timestamp,
                "last_attempted_at": timestamp,
                "last_run_status": "success",
            },
        )
        print(f"Wrote {len(events)} upcoming event(s) to data/{filename}.")
    except Exception as error:
        if csv_path is not None and csv_path.exists():
            csv_path.unlink()
        failed_at = datetime.now(timezone.utc)
        failure_metadata = {
            **previous_metadata,
            "source_id": source_id,
            "last_attempted_at": failed_at.isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
            "last_run_status": "failed",
        }
        try:
            write_metadata(metadata_path, failure_metadata)
        except Exception as metadata_error:
            raise RuntimeError(
                f"Scrape failed ({error}); failure status could not be saved "
                f"({metadata_error})."
            ) from error
        raise


def read_metadata(path, source_id):
    if not path.exists():
        return {
            "source_id": source_id,
            "file": None,
            "last_successful_at": None,
            "last_attempted_at": None,
            "last_run_status": "unknown",
        }
    with path.open(encoding="utf-8") as metadata_file:
        metadata = json.load(metadata_file)
    if metadata.get("source_id") != source_id:
        raise ValueError(f"Unexpected source id in {path}.")
    return metadata


def write_events(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as temporary_file:
        writer = csv.DictWriter(temporary_file, fieldnames=["date", "location", "url"])
        writer.writeheader()
        writer.writerows(events)
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(path)


def write_metadata(path, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary_file:
        json.dump(metadata, temporary_file, ensure_ascii=False, indent=2)
        temporary_file.write("\n")
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(path)
