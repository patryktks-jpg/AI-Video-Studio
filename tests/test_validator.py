"""Testy jednostkowe walidatora schematu JSON oraz programowej weryfikacji faktów."""

import unittest

from scripts.validator import validate_pill_document, verify_facts_against_source


def _build_valid_item(headline: str = "Krótszy nagłówek o interpretacji VAT") -> dict:
    return {
        "id": "kis-1001",
        "headline": headline,
        "summary": "Podatnik ma prawo do odliczenia 23% VAT z faktury dokumentującej zakup usługi.",
        "tags": ["VAT", "usługi"],
        "importance": "high",
        "relevance_for_profile": {
            "level": "high",
            "reason": "Dotyczy rozliczeń VAT w JDG.",
        },
        "details": {
            "what_happened": "Dyrektor KIS w interpretacji 0114-KDIP4-1.4012.500.2026.1.MK z dnia 12.11.2026 uznał prawo do odliczenia 23% VAT.",
            "background": "Wnioskodawca poniósł wydatek 1 500 zł netto na usługi informatyczne.",
            "what_it_means_for_business": "W podobnym stanie faktycznym można odliczyć VAT od usług wsparcia.",
            "what_to_do": ["Sprawdź opis na fakturze."],
            "deadlines": [{"date": "2026-11-25", "description": "Złożenie JPK_V7M"}],
            "caveats": "Interpretacja indywidualna wiąże formalnie wnioskodawcę.",
        },
        "sources": [
            {
                "name": "EUREKA MF (KIS)",
                "url": "https://eureka.mf.gov.pl/informacje/podglad/1001",
                "published": "2026-11-12",
            }
        ],
        "confidence": "high",
    }


def _build_valid_pill(item: dict) -> dict:
    return {
        "date": "2026-11-15",
        "generated_at": "2026-11-15T07:35:00+01:00",
        "weather": {"city": "Brzesko", "status": "ok"},
        "markets": {"status": "ok"},
        "deadlines": [],
        "sections": [
            {
                "id": "interpretacje",
                "title": "Interpretacje podatkowe",
                "status": "ok",
                "items": [item],
            }
        ],
    }


class TestValidator(unittest.TestCase):
    def test_valid_pill_document_passes(self) -> None:
        doc = _build_valid_pill(_build_valid_item())
        is_valid, errors = validate_pill_document(doc)
        self.assertTrue(is_valid, msg=f"Nieoczekiwane błędy: {errors}")
        self.assertEqual(errors, [])

    def test_invalid_headline_and_missing_fields_fail(self) -> None:
        bad_item = _build_valid_item(headline="A" * 120)
        del bad_item["details"]["caveats"]
        bad_item["sources"] = []
        doc = _build_valid_pill(bad_item)
        is_valid, errors = validate_pill_document(doc)
        self.assertFalse(is_valid)
        self.assertGreaterEqual(len(errors), 3)

    def test_verify_facts_against_source_matches_high(self) -> None:
        item = _build_valid_item()
        source = (
            "Sygnatura: 0114-KDIP4-1.4012.500.2026.1.MK. "
            "Data wydania: 2026-11-12. "
            "Wnioskodawca poniósł koszt 1500 zł oraz odliczył podatek w stawce 23%."
        )
        confidence, mismatches = verify_facts_against_source(item, source)
        self.assertEqual(confidence, "high", msg=f"Mismatches: {mismatches}")
        self.assertEqual(mismatches, [])

    def test_verify_facts_against_source_detects_hallucinations(self) -> None:
        item = _build_valid_item()
        item["details"]["what_happened"] = (
            "Sygnatura 0111-KDIB1-1.9999.2026.1.AB z dnia 2026-12-31 obniża stawkę do 19% oraz przyznaje ulgę 9999 zł."
        )
        source = "Interpretacja z dnia 2026-11-12 dotyczy stawki 23% oraz kwoty 1 500 zł."
        confidence, mismatches = verify_facts_against_source(item, source)
        self.assertEqual(confidence, "low")
        self.assertGreaterEqual(len(mismatches), 4)


if __name__ == "__main__":
    unittest.main()
