"""Testy jednostkowe (offline) dla modułów pobierających i parsujących źródła."""

import unittest

from scripts.sources.eureka_kis import (
    parse_eureka_document,
    score_eureka_hit,
    truncate_keeping_head_and_tail,
)
from scripts.sources.http_utils import clean_html_to_text, extract_article_body
from scripts.sources.legislation import (
    format_du_act_detail,
    format_sejm_print,
    is_business_relevant,
)
from scripts.sources.markets import parse_nbp_reference_rate_xml, parse_nbp_table_a
from scripts.sources.rss_utils import parse_rss_xml
from scripts.sources.weather import build_practical_tip, parse_weather_payload
from scripts.sources.zus_gov import (
    parse_gov_finanse_list,
    parse_polish_date,
    parse_zus_aktualnosci_list,
)


class TestWeatherSource(unittest.TestCase):
    def test_build_practical_tip_rain_and_cold(self) -> None:
        hourly = [
            {"hour": "08:00", "temp": 2.0, "rain_prob": 10},
            {"hour": "14:00", "temp": 3.0, "rain_prob": 65},
        ]
        tip = build_practical_tip(hourly, apparent_temp=2.0, wind_speed=15.0)
        self.assertIn("14:00", tip)
        self.assertIn("65%", tip)
        self.assertIn("kurtka", tip)

    def test_build_practical_tip_dry_windy(self) -> None:
        hourly = [{"hour": "10:00", "temp": 18.0, "rain_prob": 5}]
        tip = build_practical_tip(hourly, apparent_temp=18.0, wind_speed=35.0)
        self.assertIn("bez większego ryzyka opadów", tip)
        self.assertIn("wiatr", tip)

    def test_parse_weather_payload_filters_daytime_hours(self) -> None:
        payload = {
            "current": {
                "temperature_2m": 7.5,
                "apparent_temperature": 5.0,
                "weather_code": 2,
                "wind_speed_10m": 12.0,
            },
            "daily": {
                "temperature_2m_max": [9.0],
                "temperature_2m_min": [3.0],
                "precipitation_probability_max": [20],
            },
            "hourly": {
                "time": [
                    "2026-11-15T05:00",
                    "2026-11-15T08:00",
                    "2026-11-15T14:00",
                    "2026-11-15T22:00",
                ],
                "temperature_2m": [2.0, 5.5, 9.0, 4.0],
                "precipitation_probability": [0, 10, 20, 0],
            },
        }
        parsed = parse_weather_payload(payload, city="Brzesko", postal_code="32-800")
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["city"], "Brzesko")
        self.assertEqual(len(parsed["hourly_forecast"]), 2)
        self.assertEqual(parsed["hourly_forecast"][0]["hour"], "08:00")
        self.assertEqual(parsed["hourly_forecast"][1]["hour"], "14:00")


class TestMarketsSource(unittest.TestCase):
    def test_parse_nbp_table_a_orders_and_filters(self) -> None:
        payload = [
            {
                "table": "A",
                "no": "221/A/NBP/2026",
                "effectiveDate": "2026-11-13",
                "rates": [
                    {"currency": "dolar amerykański", "code": "USD", "mid": 3.98766},
                    {"currency": "jen", "code": "JPY", "mid": 0.025},
                    {"currency": "euro", "code": "EUR", "mid": 4.31234},
                ],
            }
        ]
        res = parse_nbp_table_a(payload, ["EUR", "USD"])
        self.assertEqual(res["table_no"], "221/A/NBP/2026")
        self.assertEqual([r["code"] for r in res["rates"]], ["EUR", "USD"])
        self.assertEqual(res["rates"][0]["mid"], 4.3123)
        self.assertEqual(res["rates"][1]["mid"], 3.9877)

    def test_parse_nbp_reference_rate_xml(self) -> None:
        xml_str = """<?xml version="1.0" encoding="utf-8"?>
        <stopy_procentowe>
          <tabela nazwa="podstawowe">
            <pozycja id="ref" nazwa="Stopa referencyjna" oprocentowanie="3,75" obowiazuje_od="2026-10-08"/>
            <pozycja id="lom" nazwa="Stopa lombardowa" oprocentowanie="4,25" obowiazuje_od="2026-10-08"/>
          </tabela>
        </stopy_procentowe>"""
        rate = parse_nbp_reference_rate_xml(xml_str)
        self.assertIsNotNone(rate)
        assert rate is not None
        self.assertEqual(rate["value_pct"], 3.75)
        self.assertEqual(rate["effective_from"], "2026-10-08")


class TestEurekaKisSource(unittest.TestCase):
    def test_parse_eureka_document_full_text(self) -> None:
        doc = {
            "id": 719107,
            "nazwa": "Interpretacja indywidualna",
            "dokument": {
                "fields": [
                    {"key": "ID_INFORMACJI", "value": "719107"},
                    {"key": "SYG", "value": "0114-KDIP4-1.4012.500.2026.1.MK"},
                    {"key": "TEZA", "value": "Prawo do odliczenia VAT od usług IT"},
                    {"key": "DATA_PUBLIKACJI", "value": "2026-11-14T08:00:00Z"},
                    {"key": "DT_WYD", "value": "2026-11-10T00:00:00Z"},
                    {
                        "key": "TRESC_INTERESARIUSZ",
                        "value": "<p>Stan faktyczny: Spółka świadczy usługi.</p><p>Stanowisko prawidłowe.</p>",
                    },
                ]
            },
        }
        hit = {"SLOWA_KLUCZOWE": ["VAT", "odliczenie"], "KATEGORIA_INFORMACJI": ["Interpretacja indywidualna"]}
        parsed = parse_eureka_document(doc, hit)
        self.assertEqual(parsed["id"], "kis-719107")
        self.assertEqual(parsed["section_id"], "interpretacje")
        self.assertEqual(parsed["published"], "2026-11-14")
        self.assertIn("0114-KDIP4-1.4012.500.2026.1.MK", parsed["full_text"])
        self.assertIn("Spółka świadczy usługi.", parsed["full_text"])
        self.assertNotIn("<p>", parsed["full_text"])

    def test_score_eureka_hit_and_head_tail_truncation(self) -> None:
        self.assertEqual(score_eureka_hit({"TEZA": "Odliczanie VAT na cmentarze komunalne", "SLOWA_KLUCZOWE": ["VAT"]}), -1)
        self.assertGreater(score_eureka_hit({"TEZA": "Ryczałt w działalności gospodarczej B2B", "SLOWA_KLUCZOWE": ["ryczałt"]}), 0)

        long_text = "POCZATEK_STAN_FAKTYCZNY " + ("X" * 900) + " KONIEC_UZASADNIENIE"
        truncated = truncate_keeping_head_and_tail(long_text, 500)
        self.assertLessEqual(len(truncated), 500)
        self.assertIn("POCZATEK_STAN_FAKTYCZNY", truncated)
        self.assertIn("KONIEC_UZASADNIENIE", truncated)


class TestLegislationSource(unittest.TestCase):
    def test_business_relevance_filter(self) -> None:
        self.assertTrue(is_business_relevant("Projekt ustawy o podatku VAT i KSeF"))
        self.assertFalse(is_business_relevant("Uchwała w sprawie ustanowienia roku patrona"))
        self.assertFalse(is_business_relevant("Rozporządzenie w sprawie opłat za krew i jej składniki"))
        self.assertFalse(is_business_relevant("Nadanie statutu Wody Polskie"))

    def test_format_du_act_detail(self) -> None:
        act = {
            "ELI": "DU/2026/1495",
            "displayAddress": "Dz.U. 2026 poz. 1495",
            "title": "Rozporządzenie w sprawie JPK_VAT",
            "promulgation": "2026-11-12",
            "entryIntoForce": "2026-12-01",
            "status": "obowiązujący",
            "type": "Rozporządzenie",
            "releasedBy": ["Minister Finansów"],
            "keywords": ["VAT", "JPK"],
            "comments": "art. 1 wchodzi od 2027-01-01",
            "directives": [{"address": "32025L0516", "title": "Dyrektywa VAT w epoce cyfrowej"}],
        }
        res = format_du_act_detail(act, process_desc="Upraszcza korygowanie JPK.")
        self.assertEqual(res["id"], "eli-du-2026-1495")
        self.assertEqual(res["section_id"], "podatki_zus")
        self.assertIn("2026-12-01", res["full_text"])
        self.assertIn("Dyrektywa VAT w epoce cyfrowej", res["full_text"])
        self.assertIn("Upraszcza korygowanie JPK.", res["full_text"])

    def test_format_sejm_print(self) -> None:
        pr = {"number": "123", "title": "Zmiana ustawy o ZUS", "deliveryDate": "2026-11-10", "term": 10}
        proc = {"description": "Skierowano do komisji", "passed": False, "stages": [{"date": "2026-11-11", "stageName": "I czytanie"}]}
        res = format_sejm_print(pr, proc)
        self.assertEqual(res["id"], "sejm-druk-10-123")
        self.assertIn("I czytanie", res["full_text"])


class TestZusGovAndRssAndHtml(unittest.TestCase):
    def test_parse_polish_date(self) -> None:
        self.assertEqual(parse_polish_date("15.11.2026"), "2026-11-15")
        self.assertEqual(parse_polish_date("22 października 2026 r."), "2026-10-22")

    def test_parse_gov_finanse_list(self) -> None:
        html_doc = """
        <div class="art-prev">
          <span class="date">14.11.2026</span>
          <div class="title"><a href="/web/finanse/komunikat-vat">Nowe objaśnienia VAT</a></div>
        </div>"""
        items = parse_gov_finanse_list(html_doc, limit=3)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://www.gov.pl/web/finanse/komunikat-vat")
        self.assertEqual(items[0]["published"], "2026-11-14")

    def test_parse_zus_aktualnosci_list(self) -> None:
        html_doc = """
        <a href="https://www.zus.pl/-/nowe-skladki-2027?redirect=%2Fo-zus%2Faktualnosci">Ważny komunikat ZUS dla firm</a>
        <a href="https://www.zus.pl/-/krotki?redirect=%2Fo-zus%2Faktualnosci">Więcej</a>
        """
        items = parse_zus_aktualnosci_list(html_doc, limit=5)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://www.zus.pl/-/nowe-skladki-2027")

    def test_parse_rss_xml(self) -> None:
        rss_bytes = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
          <item>
            <title>Kurs euro i inflacja</title>
            <link>https://example.com/news/1</link>
            <description>&lt;p&gt;Krotki opis gospodarki.&lt;/p&gt;</description>
            <pubDate>Sat, 14 Nov 2026 09:30:00 +0100</pubDate>
          </item>
        </channel></rss>"""
        entries = parse_rss_xml(rss_bytes, source_name="TestRSS", limit=5)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["published"], "2026-11-14")
        self.assertEqual(entries[0]["description"], "Krotki opis gospodarki.")

    def test_extract_article_body_and_clean_html(self) -> None:
        cleaned = clean_html_to_text("<p>Linia &amp; pierwsza</p><div>Linia druga</div>")
        self.assertEqual(cleaned, "Linia & pierwsza\nLinia druga")

        page = """
        <nav><ul><li>Menu glowne nawigacyjne portalu</li></ul></nav>
        <div class="journal-content-article">
          <p>To jest właściwy akapit komunikatu podatkowego o długości ponad dwudziestu pięciu znaków.</p>
        </div>
        <script>console.log('ignored script content over 25 chars');</script>
        """
        body = extract_article_body(page)
        self.assertIn("właściwy akapit komunikatu", body)
        self.assertNotIn("Menu glowne", body)
        self.assertNotIn("console.log", body)


if __name__ == "__main__":
    unittest.main()
