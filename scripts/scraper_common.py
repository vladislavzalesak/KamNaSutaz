"""Shared helpers for the independent event calendar scrapers."""

import csv
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

DATE_PATTERN = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b")
ROOT = Path(__file__).resolve().parents[1]
SQUAD_CA_CHAIN_PATH = ROOT / "scripts" / "certs" / "squad-ca-chain.pem"
DETAIL_HOSTS = {
    "los-sk": {"los-sk.sk", "www.los-sk.sk"},
    "sads": {"new.sads.sk", "sads.sk"},
    "shootingarea": {"www.shootingarea.eu", "shootingarea.eu"},
    "squad": {"squad.sk", "www.squad.sk"},
}


def parse_date(value):
    match = DATE_PATTERN.search(value)
    if match is None:
        return None
    return datetime.strptime(match.group(), "%d.%m.%Y").date()


def make_event(event_date, location, url, name=""):
    if not location or not url:
        raise ValueError("Found a competition row without a location or detail link.")
    return {
        "date": event_date.isoformat(),
        "name": " ".join(name.split()),
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
        name_column=None,
    ):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.date_column = date_column
        self.location_column = location_column
        self.link_column = link_column
        self.row_classes = row_classes
        self.name_column = name_column
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
        if self.name_column == self.location_column:
            name = location_lines[0] if len(location_lines) > 1 else ""
        elif self.name_column is not None and self.name_column < len(cells):
            name = " ".join("".join(cells[self.name_column]["text"]).split())
        else:
            name = ""
        links = cells[self.link_column]["links"]
        self.events.append(
            make_event(
                event_date,
                location,
                links[0] if links else "",
                name,
            )
        )


def parse_table_events(
    html,
    base_url,
    today,
    date_column,
    location_column,
    link_column,
    row_classes=None,
    name_column=None,
):
    parser = TableEventParser(
        base_url,
        date_column,
        location_column,
        link_column,
        row_classes,
        name_column,
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
    if urlsplit(url).hostname in {"squad.sk", "www.squad.sk"}:
        context.load_verify_locations(cafile=str(SQUAD_CA_CHAIN_PATH))
    with urlopen(request, timeout=30, context=context) as response:
        return response.read().decode("utf-8")


class CompetitionTypeParser(HTMLParser):
    """Collect visible text and labeled event details from HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.fields = {}
        self.ignored_tags = []
        self.row = None
        self.cell = None
        self.span_kind = None
        self.span_text = []
        self.current_label = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored_tags.append(tag)
            return
        if self.ignored_tags:
            return

        attributes = dict(attrs)
        if tag == "tr":
            self.row = []
        elif tag in {"th", "td"} and self.row is not None:
            self.cell = []
        elif tag == "span":
            classes = set(attributes.get("class", "").split())
            if "modry" in classes:
                self.span_kind = "label"
                self.span_text = []
            elif "biely" in classes:
                self.span_kind = "value"
                self.span_text = []
        elif tag == "img":
            alt = attributes.get("alt", "")
            if re.search(r"\b(?:IPSC|IDPA|PRS|Steel)\b", alt, re.IGNORECASE):
                self.parts.append(alt)

    def handle_endtag(self, tag):
        if self.ignored_tags and tag == self.ignored_tags[-1]:
            self.ignored_tags.pop()
            return
        if self.ignored_tags:
            return

        if tag == "span" and self.span_kind:
            value = " ".join("".join(self.span_text).split())
            if self.span_kind == "label":
                self.current_label = value.casefold()
            elif self.current_label:
                self.fields[self.current_label] = value
                self.current_label = None
            self.span_kind = None
            self.span_text = []
        elif tag in {"th", "td"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if len(self.row) > 1 and self.row[0]:
                self.fields[self.row[0].casefold()] = self.row[1]
            self.row = None

    def handle_data(self, data):
        if not self.ignored_tags:
            self.parts.append(data)
            if self.cell is not None:
                self.cell.append(data)
            if self.span_kind:
                self.span_text.append(data)


def _classify_type_text(text):
    if re.search(r"\bsteel\s*(?:cup|challenge)\b", text, re.IGNORECASE):
        return "Steel Cup/Challenge"
    if re.search(r"\bidpa\b", text, re.IGNORECASE):
        return "IDPA"
    if re.search(r"\bprs\b|precision\s+rifle\s+series", text, re.IGNORECASE):
        return "PRS"
    if re.search(r"action\s*air", text, re.IGNORECASE):
        return (
            "IPSC Action Air"
            if re.search(r"\bipsc\b", text, re.IGNORECASE)
            else "Action Air"
        )
    if re.search(r"\bipsc\b", text, re.IGNORECASE):
        if re.search(r"\b(?:mini\s*)?rifle\b", text, re.IGNORECASE):
            return "IPSC Rifle/Mini Rifle"
        return "IPSC"
    return ""


def _squad_difficulty(text):
    match = re.search(
        r"\bObtížnost\s*:\s*(.{1,140}?)(?=\b(?:Počet situací|"
        r"Minimální počet ran|Prematch|Hlavní závod)\b|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1) if match else ""


def classify_competition_type(html, event_name="", source_id=""):
    parser = CompetitionTypeParser()
    parser.feed(re.sub(r"<(script|style)\b.*?</\1\s*>", "", html, flags=re.I | re.S))
    if source_id == "sads":
        rules = parser.fields.get("pretek podľa pravidiel", "")
        discipline = parser.fields.get("druh preteku", "")
        return _classify_type_text(f"{rules} {discipline} {event_name}")

    if source_id == "shootingarea":
        page_text = " ".join(parser.parts)
        if re.search(r"\bsteel\s*(?:cup|challenge)\b", page_text, re.IGNORECASE):
            return "Steel Cup/Challenge"
        return _classify_type_text(event_name)

    event_type = _classify_type_text(event_name)
    if event_type:
        return event_type

    if source_id == "squad":
        difficulty = _squad_difficulty(" ".join(parser.parts))
        return _classify_type_text(f"{difficulty} {event_name}")
    return ""


def enrich_event_types(events, source_id, fetcher=None):
    if source_id not in DETAIL_HOSTS:
        raise ValueError(f"Unknown competition source: {source_id}")
    detail_fetcher = fetcher or fetch_html

    for event in events:
        parsed_url = urlsplit(event["url"])
        if (
            parsed_url.scheme not in {"http", "https"}
            or parsed_url.hostname not in DETAIL_HOSTS[source_id]
        ):
            print(
                f"Skipping competition type lookup for untrusted URL: {event['url']}",
                file=sys.stderr,
            )
            event["type"] = ""
            continue

        try:
            detail_html = detail_fetcher(event["url"])
        except OSError as error:
            print(
                f"Could not load competition type for {event['url']}: {error}",
                file=sys.stderr,
            )
            event["type"] = ""
            continue

        event["type"] = classify_competition_type(
            detail_html,
            event["name"],
            source_id,
        )
    return events


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
                "last_error": None,
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
            "last_error": str(error)[:500],
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
            "last_error": None,
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
        writer = csv.DictWriter(
            temporary_file,
            fieldnames=["date", "name", "location", "url", "type"],
        )
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
