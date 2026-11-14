import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scrape_los_sk import parse_events


class ParseEventsTests(unittest.TestCase):
    def test_extracts_only_upcoming_events_and_sorts_them(self):
        html = """
        <table id="cal2"><tbody>
          <tr><td></td><td><a href="/competition/2">20.02.2027</a></td><td>Miesto, mesto</td></tr>
          <tr><td></td><td><a href="/competition/1">13.11.2026</a></td><td>Minulá súťaž</td></tr>
          <tr><td></td><td><a href="/competition/3">14.11.2026</a></td><td>Dnes</td></tr>
        </tbody></table>
        """

        self.assertEqual(
            parse_events(html, date(2026, 11, 14)),
            [
                {
                    "date": "2026-11-14",
                    "location": "Dnes",
                    "url": "https://los-sk.sk/competition/3",
                },
                {
                    "date": "2027-02-20",
                    "location": "Miesto, mesto",
                    "url": "https://los-sk.sk/competition/2",
                },
            ],
        )

    def test_fails_if_expected_table_is_missing(self):
        with self.assertRaisesRegex(ValueError, "expected #cal2 table"):
            parse_events("<html></html>", date(2026, 11, 14))


if __name__ == "__main__":
    unittest.main()
