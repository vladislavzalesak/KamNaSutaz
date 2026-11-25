import sys
import json
import ssl
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scraper_common
import restore_pages_data
import duplicate_thresholds
from scraper_common import (
    classify_competition_type,
    enrich_event_types,
    fetch_html,
    parse_date,
    write_events,
)
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

    def test_fetch_html_loads_squad_chain_without_disabling_tls(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"page"

        with mock.patch.object(
            scraper_common, "urlopen", return_value=response
        ) as open_url:
            self.assertEqual(fetch_html("https://squad.sk/"), "page")

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
            csv_path = root / "data" / manifest["file"]
            self.assertTrue(csv_path.is_file())
            self.assertEqual(
                csv_path.read_text(encoding="utf-8").splitlines()[0],
                "date,name,location,url,type",
            )
            self.assertTrue(manifest["last_successful_at"].endswith("Z"))
            self.assertEqual(manifest["last_run_status"], "success")
            self.assertIsNone(manifest["last_error"])

    def test_write_events_includes_optional_competition_type(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "events.csv"
            write_events(
                csv_path,
                [
                    {
                        "date": "2026-12-05",
                        "name": "Action Air",
                        "location": "Vsetín",
                        "url": "https://example.test/event",
                        "type": "IPSC Action Air",
                    },
                    {
                        "date": "2026-12-06",
                        "name": "Unknown",
                        "location": "Trenčín",
                        "url": "https://example.test/unknown",
                    },
                ],
            )

            self.assertEqual(
                csv_path.read_text(encoding="utf-8").splitlines(),
                [
                    "date,name,location,url,type",
                    "2026-12-05,Action Air,Vsetín,https://example.test/event,IPSC Action Air",
                    "2026-12-06,Unknown,Trenčín,https://example.test/unknown,",
                ],
            )

    def test_sads_classification_uses_event_fields_not_site_navigation(self):
        self.assertEqual(
            classify_competition_type(
                """
                <nav>Action Air IPSC</nav>
                <div><span class="modry">Pretek podľa pravidiel</span>
                  <span class="biely">IPSC</span></div>
                <div><span class="modry">Druh preteku</span>
                  <span class="biely">HG+PCC</span></div>
                """,
                "Falcon League",
                "sads",
            ),
            "IPSC",
        )
        self.assertEqual(
            classify_competition_type(
                """
                <tr><th>Pretek podľa pravidiel</th><td>IPSC</td></tr>
                <tr><th>Druh preteku</th>
                  <td>Action Air HG, Action Air PCC</td></tr>
                """,
                "CNC Action Air",
                "sads",
            ),
            "IPSC Action Air",
        )
        self.assertEqual(
            classify_competition_type(
                """
                <nav>IPSC Action Air</nav>
                <div><span class="modry">Pretek podľa pravidiel</span>
                  <span class="biely">Steel Cup/Challenge</span></div>
                """,
                "Speed Steel",
                "sads",
            ),
            "Steel Cup/Challenge",
        )
        self.assertEqual(
            classify_competition_type(
                "<nav>Action Air IPSC</nav>",
                "Bellator Armory",
                "sads",
            ),
            "",
        )
        self.assertEqual(
            classify_competition_type(
                "<div>Obtížnost: IPSC Level 1. HG + PCC\n"
                "Počet situací: 8</div>",
                "Atlas One",
                "squad",
            ),
            "IPSC",
        )
        self.assertEqual(
            classify_competition_type(
                "<div>Obtížnost: SteelCup - viz pravidla\n"
                "Počet situací: 8</div>",
                "Atlas HellsBells",
                "squad",
            ),
            "Steel Cup/Challenge",
        )
        self.assertEqual(
            classify_competition_type(
                "<header>Shooting Area Kalendár IPSC pretekov</header>"
                "<main>IPSC MATCH REGISTRATION</main>",
                "Komarnanska puska",
                "shootingarea",
            ),
            "",
        )
        self.assertEqual(
            classify_competition_type(
                "<main>Steel Cup/Challenge</main>",
                "Atlas HellsBells",
                "shootingarea",
            ),
            "Steel Cup/Challenge",
        )

    def test_type_lookup_rejects_external_hosts_without_fetching(self):
        events = [
            {
                "date": "2026-12-05",
                "name": "External",
                "location": "Somewhere",
                "url": "https://unexpected.example/event",
            }
        ]
        fetcher = mock.Mock()

        self.assertEqual(enrich_event_types(events, "sads", fetcher), events)
        self.assertEqual(events[0]["type"], "")
        fetcher.assert_not_called()

    def test_type_lookup_adds_type_from_sads_detail_fields(self):
        events = [
            {
                "date": "2026-12-05",
                "name": "CNC ACTION AIR",
                "location": "Vsetín",
                "url": "https://new.sads.sk/event/1",
            }
        ]
        detail_html = """
        <tr><th>Pretek podľa pravidiel</th><td>IPSC</td></tr>
        <tr><th>Druh preteku</th><td>Action Air HG, Action Air PCC</td></tr>
        """

        with mock.patch(
            "scraper_common.fetch_html", return_value=detail_html
        ) as fetch:
            enrich_event_types(events, "sads")

        self.assertEqual(events[0]["type"], "IPSC Action Air")
        fetch.assert_called_once_with(events[0]["url"])

    def test_type_lookup_handles_unavailable_details_and_reports_failure(self):
        events = [
            {
                "date": "2026-12-05",
                "name": "Known",
                "location": "Somewhere",
                "url": "https://new.sads.sk/event/1",
            }
        ]
        with (
            mock.patch(
                "scraper_common.fetch_html",
                side_effect=OSError("detail unavailable"),
            ),
            mock.patch("builtins.print") as print_warning,
        ):
            enrich_event_types(events, "sads")

        self.assertEqual(events[0]["type"], "")
        self.assertIn("detail unavailable", print_warning.call_args.args[0])
        self.assertIs(print_warning.call_args.kwargs["file"], sys.stderr)

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
            self.assertEqual(manifest["last_error"], "source unavailable")
            self.assertNotEqual(
                manifest["last_attempted_at"], previous["last_attempted_at"]
            )

    def test_empty_scrape_preserves_previous_data_and_records_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            previous_csv = "los-sk_20261107T041700000000Z.csv"
            previous = {
                "source_id": "los-sk",
                "file": previous_csv,
                "last_successful_at": "2026-11-07T04:17:00.000000Z",
                "last_attempted_at": "2026-11-07T04:17:00.000000Z",
                "last_run_status": "success",
            }
            csv_content = b"date,name,location,url,type\n"
            (data / "los-sk.json").write_text(json.dumps(previous), encoding="utf-8")
            (data / previous_csv).write_bytes(csv_content)
            with (
                mock.patch.object(scraper_common, "ROOT", root),
                mock.patch.object(scraper_common, "fetch_html", return_value="calendar"),
                self.assertRaisesRegex(ValueError, "No competition dates found"),
            ):
                scraper_common.run_scraper(
                    "https://example.test",
                    "los-sk",
                    mock.Mock(
                        side_effect=ValueError("No competition dates found")
                    ),
                )

            manifest = json.loads((data / "los-sk.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["file"], previous_csv)
            self.assertEqual((data / previous_csv).read_bytes(), csv_content)
            self.assertEqual(manifest["last_run_status"], "failed")
            self.assertEqual(manifest["last_error"], "No competition dates found")

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
                    "name": "",
                    "location": "Dnes",
                    "url": "https://los-sk.sk/competition/3",
                },
                {
                    "date": "2027-02-05",
                    "name": "",
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
                    "name": "Event name",
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
                    "name": "Event name",
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
                    "name": "Match",
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
                    "name": "Match",
                    "location": "First venue",
                    "url": "https://new.sads.sk/event?id=1",
                },
                {
                    "date": "2026-12-06",
                    "name": "Match",
                    "location": "Second venue",
                    "url": "https://new.sads.sk/event?id=2",
                },
            ],
        )


class RestorePagesDataTests(unittest.TestCase):
    def test_restores_only_manifest_referenced_csv(self):
        manifest = {
            "source_id": "los-sk",
            "file": "los-sk_20261115T074253077269Z.csv",
        }
        csv_content = b"date,name,location,url\n"
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with (
                mock.patch.object(restore_pages_data, "SOURCES", ("los-sk",)),
                mock.patch.object(
                    restore_pages_data,
                    "fetch_bytes",
                    side_effect=[
                        json.dumps(manifest).encode(),
                        csv_content,
                        HTTPError(
                            "https://example.test/KamNaSutaz/duplicate-thresholds.json",
                            404,
                            "Not Found",
                            {},
                            None,
                        ),
                    ],
                ) as fetch,
            ):
                restore_pages_data.restore_pages_data(
                    "https://example.test/KamNaSutaz", data_dir
                )

            self.assertEqual(
                (data_dir / "los-sk.json").read_bytes(),
                json.dumps(manifest).encode(),
            )
            self.assertEqual(
                (data_dir / manifest["file"]).read_bytes(), csv_content
            )
            self.assertEqual(
                [call.args[0] for call in fetch.call_args_list],
                [
                    "https://example.test/KamNaSutaz/data/los-sk.json",
                    f"https://example.test/KamNaSutaz/data/{manifest['file']}",
                    "https://example.test/KamNaSutaz/duplicate-thresholds.json",
                ],
            )

    def test_restores_published_duplicate_thresholds(self):
        config = {
            "possible_threshold": 0.7,
            "strict_threshold": 0.9,
        }
        config_bytes = json.dumps(config).encode()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thresholds_path = root / "duplicate-thresholds.json"
            with (
                mock.patch.object(restore_pages_data, "SOURCES", ()),
                mock.patch.object(
                    restore_pages_data, "fetch_bytes", return_value=config_bytes
                ),
            ):
                restore_pages_data.restore_pages_data(
                    "https://example.test/KamNaSutaz",
                    root / "data",
                    thresholds_path,
                )

            self.assertEqual(json.loads(thresholds_path.read_text()), config)

    def test_missing_published_manifest_is_allowed_for_first_deployment(self):
        not_found = HTTPError(
            "https://example.test/data/los-sk.json", 404, "Not Found", {}, None
        )
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(
                restore_pages_data, "fetch_bytes", side_effect=not_found
            ):
                restore_pages_data.restore_pages_data(
                    "https://example.test/KamNaSutaz", Path(directory)
                )

            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_rejects_unexpected_csv_filename(self):
        manifest = {"source_id": "los-sk", "file": "../untrusted.csv"}
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(
                restore_pages_data,
                "fetch_bytes",
                return_value=json.dumps(manifest).encode(),
            ) as fetch:
                with self.assertRaisesRegex(ValueError, "Invalid CSV filename"):
                    restore_pages_data.restore_pages_data(
                        "https://example.test/KamNaSutaz", Path(directory)
                    )

            fetch.assert_called_once()


class DuplicateThresholdsTests(unittest.TestCase):
    def test_writes_percent_inputs_as_valid_fractional_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate-thresholds.json"
            config = duplicate_thresholds.write_config(70, 90, path)

            self.assertEqual(
                config,
                {"possible_threshold": 0.7, "strict_threshold": 0.9},
            )
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), config)

    def test_rejects_invalid_order_and_out_of_range_percentages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate-thresholds.json"
            for possible, strict in ((70, 60), (-1, 90), (50, 101)):
                with self.subTest(possible=possible, strict=strict):
                    with self.assertRaises(ValueError):
                        duplicate_thresholds.write_config(possible, strict, path)


if __name__ == "__main__":
    unittest.main()
