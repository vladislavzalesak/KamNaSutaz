"""Restore the last published data snapshot before running the scrapers."""

import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("los-sk", "squad", "shootingarea", "sads")


def fetch_bytes(url):
    request = Request(url, headers={"User-Agent": "KamNaSutaz event calendar"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def restore_pages_data(base_url, data_dir=ROOT / "data"):
    base_url = f"{base_url.rstrip('/')}/"
    data_dir.mkdir(parents=True, exist_ok=True)

    for source_id in SOURCES:
        manifest_url = urljoin(base_url, f"data/{source_id}.json")
        try:
            manifest_bytes = fetch_bytes(manifest_url)
        except HTTPError as error:
            if error.code == 404:
                continue
            raise

        manifest = json.loads(manifest_bytes.decode("utf-8"))
        if not isinstance(manifest, dict) or manifest.get("source_id") != source_id:
            raise ValueError(f"Unexpected source id in published {source_id} manifest.")

        filename = manifest.get("file")
        csv_bytes = None
        if filename is not None:
            filename_pattern = re.compile(
                rf"^{re.escape(source_id)}_\d{{8}}T\d{{12}}Z\.csv$"
            )
            if not isinstance(filename, str) or not filename_pattern.fullmatch(filename):
                raise ValueError(f"Invalid CSV filename in published {source_id} manifest.")
            csv_bytes = fetch_bytes(urljoin(base_url, f"data/{filename}"))

        if csv_bytes is not None:
            (data_dir / filename).write_bytes(csv_bytes)
        (data_dir / f"{source_id}.json").write_bytes(manifest_bytes)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: restore_pages_data.py <pages-base-url>")
    restore_pages_data(sys.argv[1])
