import sys
import json
import ssl
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scraper_common
from scraper_common import fetch_html, parse_date
from scrape_los_sk import parse_events as parse_los_sk
from scrape_sads import parse_events as parse_sads
from scrape_shootingarea import parse_events as parse_shootingarea
from scrape_squad import parse_events as parse_squad


TODAY = date(2026, 11, 14)


class ParseEventsTests(unittest.TestCase):
    def test_fetch_html_uses_verified_context_with_certifi_roots(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"page"

        with mock.patch.object(
            scraper_common, "urlopen", return_value=response
        ) as open_url:
            self.assertEqual(fetch_html("https://example.test"), "page")

        context = open_url.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_los_sk_reads_single_digit_day_and_month(self):
        self.assertEqual(parse_date("5.2.2027"), date(2027, 2, 5))

    def test_successful_scrape_writes_timestamped_csv_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(scraper_common, "ROOT", root),
                mock.patch.object(scraper_common, "fetch_html", return_value=""),
            ):
                scraper_common.run_scraper("https://example.test", "los-sk", lambda *_: [])

            manifest = json.loads((root / "data" / "los-sk.json").read_text())
            self.assertRegex(manifest["file"], r"^los-sk_\d{8}T\d{12}Z\.csv$")
            self.assertTrue((root / "data" / manifest["file"]).is_file())
            self.assertTrue(manifest["last_successful_at"].endswith("Z"))
            self.assertEqual(manifest["last_run_status"], "success")

    def test_failed_scrape_preserves_previous_success_and_records_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            previous = {
                "source_id": "los-sk",
                "file": "los-sk_20261107T041700000000Z.csv",
                "last_successful_at": "2026-11-07T04:17:00.000000Z",
                "last_attempted_at": "2026-11-07T04:17:00.000000Z",
                "last_run_status": "success",
            }
            (data / "los-sk.json").write_text(json.dumps(previous), encoding="utf-8")
            with (
                mock.patch.object(scraper_common, "ROOT", root),
                mock.patch.object(
                    scraper_common,
                    "fetch_html",
                    side_effect=OSError("source unavailable"),
                ),
                self.assertRaisesRegex(OSError, "source unavailable"),
            ):
                scraper_common.run_scraper(
                    "https://example.test", "los-sk", lambda *_: []
                )

            manifest = json.loads((data / "los-sk.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["file"], previous["file"])
            self.assertEqual(
                manifest["last_successful_at"], previous["last_successful_at"]
            )
            self.assertEqual(manifest["last_run_status"], "failed")
            self.assertNotEqual(
                manifest["last_attempted_at"], previous["last_attempted_at"]
            )

    def test_los_sk_reads_displayed_dates_and_sorts(self):
        html = """
        <table id="cal2"><tbody>
          <tr><td></td><td><a href="/competition/2">5.2.2027</a></td><td>Miesto, mesto</td></tr>
          <tr><td></td><td><a href="/competition/1">13.11.2026</a></td><td>Minulá súťaž</td></tr>
          <tr><td></td><td><a href="/competition/3">14.11.2026</a></td><td>Dnes</td></tr>
        </tbody></table>
        """

        self.assertEqual(
            parse_los_sk(html, TODAY),
            [
                {
                    "date": "2026-11-14",
                    "location": "Dnes",
                    "url": "https://los-sk.sk/competition/3",
                },
                {
                    "date": "2027-02-05",
                    "location": "Miesto, mesto",
                    "url": "https://los-sk.sk/competition/2",
                },
            ],
        )

    def test_squad_reads_event_cards_and_ignores_past_dates(self):
        html = """
        <div class="zavod budouci">
          <div class="datum">5.12.2026</div>
          <div class="name">Event name</div>
          <div class="misto"><img src="flag.png"></div>
          <div class="misto">Vsetín, Czech Republic</div>
          <div class="detail"><a href="http://www.squad.sk/event">detail</a></div>
        </div>
        <div class="zavod stary">
          <div class="datum">7.11.2026</div><div class="misto">Past venue</div>
          <div class="detail"><a href="/past">detail</a></div>
        </div>
        """

        self.assertEqual(
            parse_squad(html, TODAY),
            [
                {
                    "date": "2026-12-05",
                    "location": "Vsetín, Czech Republic",
                    "url": "http://www.squad.sk/event",
                }
            ],
        )

    def test_shootingarea_reads_date_location_and_info_link(self):
        html = """
        <table>
          <tr class="tab_as">
            <td>05.12.2026<br>&nbsp;</td><td>SVK</td>
            <td class="city"><span>Event name</span><br>Strelnica, Trenčín</td>
            <td>1</td><td>ON</td><td>5 STAGE</td>
            <td><a href="sk/match-area/info/123/event">INFO</a></td>
          </tr>
        </table>
        """

        self.assertEqual(
            parse_shootingarea(html, TODAY),
            [
                {
                    "date": "2026-12-05",
                    "location": "Strelnica, Trenčín",
                    "url": "https://www.shootingarea.eu/sk/match-area/info/123/event",
                }
            ],
        )

    def test_sads_reads_calendar_date_venue_and_event_link(self):
        html = """
        <table><tr>
          <td></td><td></td><td>05.12.2026</td>
          <td><a href="/index.php?option=com_kalendar&amp;view=pretek&amp;id=30">Match</a></td>
          <td>HG</td><td>LEVEL 1</td><td>Vtáčie údolie</td>
          <td>6/123</td><td></td><td></td>
        </tr></table>
        """

        self.assertEqual(
            parse_sads(html, TODAY),
            [
                {
                    "date": "2026-12-05",
                    "location": "Vtáčie údolie",
                    "url": "https://new.sads.sk/index.php?option=com_kalendar&view=pretek&id=30",
                }
            ],
        )

    def test_sads_follows_pagination_and_deduplicates_events(self):
        first_page = """
        <table>
          <tr><td></td><td></td><td>05.11.2026</td><td><a href="/event?id=old">Match</a></td><td>HG</td><td>LEVEL 1</td><td>Old venue</td></tr>
          <tr><td></td><td></td><td>05.12.2026</td><td><a href="/event?id=1">Match</a></td><td>HG</td><td>LEVEL 1</td><td>First venue</td></tr>
        </table>
        <a href="/index.php?option=com_kalendar&amp;view=preteky&amp;Itemid=414&amp;limitstart=20">Next</a>
        """
        second_page = """
        <table>
          <tr><td></td><td></td><td>05.12.2026</td><td><a href="/event?id=1">Match</a></td><td>HG</td><td>LEVEL 1</td><td>First venue</td></tr>
          <tr><td></td><td></td><td>06.12.2026</td><td><a href="/event?id=2">Match</a></td><td>HG</td><td>LEVEL 1</td><td>Second venue</td></tr>
        </table>
        """
        next_page_url = (
            "https://new.sads.sk/index.php?option=com_kalendar"
            "&view=preteky&Itemid=414&limitstart=20"
        )

        with mock.patch("scrape_sads.fetch_html", return_value=second_page) as fetch:
            events = parse_sads(first_page, TODAY)

        fetch.assert_called_once_with(next_page_url)
        self.assertEqual(
            events,
            [
                {
                    "date": "2026-12-05",
                    "location": "First venue",
                    "url": "https://new.sads.sk/event?id=1",
                },
                {
                    "date": "2026-12-06",
                    "location": "Second venue",
                    "url": "https://new.sads.sk/event?id=2",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
