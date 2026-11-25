#!/usr/bin/env python3
"""Scrape upcoming SZVVZ competitions from its annual calendar PDF."""

import sys
from io import BytesIO
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import urlopen

from pypdf import PdfReader

from scraper_common import make_event, parse_date, run_scraper, upcoming_events

SOURCE_URL = "https://www.szvvz.sk/kalendar/"
SOURCE_ID = "szvvz"
BASE_URL = "https://www.szvvz.sk/"


class PdfLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            link = urljoin(BASE_URL, href)
            if ".pdf" in link.lower():
                self.links.append(link)


def fetch_pdf(url):
    # urllib bytes are needed here because PDF is not UTF-8 text.
    from urllib.request import Request
    req = Request(url, headers={"User-Agent": "KamNaSutaz event calendar scraper"})
    with urlopen(req, timeout=30) as response:
        return response.read()


def parse_pdf_text(pdf_bytes):
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_events(html, today):
    link_parser = PdfLinkParser()
    link_parser.feed(html)
    calendar_links = [
        link for link in link_parser.links
        if "kalendar" in link.lower() or "kalendár" in link.lower()
    ]
    if not calendar_links:
        raise ValueError("No SZVVZ calendar PDF link found.")

    text = parse_pdf_text(fetch_pdf(calendar_links[0]))
    events = []
    import re
    for line in text.splitlines():
        match = re.search(r"\b\d{1,2}[.]\d{1,2}[.]\d{4}\b", line)
        if not match:
            continue
        event_date = parse_date(match.group())
        if event_date is None:
            continue
        remainder = " ".join(line[match.end():].strip(" -|").split())
        if not remainder:
            remainder = "SZVVZ competition"
        events.append(
            make_event(
                event_date,
                "Slovensko",
                calendar_links[0],
                remainder,
            )
        )
    if not events:
        raise ValueError("No SZVVZ competition dates found in calendar PDF.")
    unique = {(event["date"], event["name"], event["url"]): event for event in events}
    return upcoming_events(unique.values(), today)


def parse_typed_events(html, today):
    events = parse_events(html, today)
    for event in events:
        event["type"] = ""
    return events


if __name__ == "__main__":
    try:
        run_scraper(SOURCE_URL, SOURCE_ID, parse_typed_events)
    except Exception as error:
        print(f"SZVVZ scrape failed: {error}", file=sys.stderr)
        raise
