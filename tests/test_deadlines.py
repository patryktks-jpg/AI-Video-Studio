"""Testy jednostkowe programowego kalkulatora terminów podatkowych i ZUS."""

import datetime
import json
import unittest
from pathlib import Path

from scripts.deadlines_calc import (
    compute_upcoming_deadlines,
    generate_ics_calendar,
    shift_to_business_day,
)


class TestDeadlinesCalculator(unittest.TestCase):
    def test_shift_weekend_to_monday(self) -> None:
        # 2026-11-15 to niedziela -> przesunięcie na poniedziałek 2026-11-16
        self.assertEqual(
            shift_to_business_day(datetime.date(2026, 11, 15)),
            datetime.date(2026, 11, 16),
        )

    def test_shift_saturday_holiday_to_monday(self) -> None:
        # 2026-08-15 to sobota i Święto Wniebowzięcia NMP -> poniedziałek 2026-08-17
        self.assertEqual(
            shift_to_business_day(datetime.date(2026, 8, 15)),
            datetime.date(2026, 8, 17),
        )

    def test_shift_christmas_chain_with_wigilia(self) -> None:
        # 2026-12-24 (czwartek, Wigilia wolna od 2025 r.), 25 (pt), 26 (sob), 27 (nd) -> 2026-12-28 (pn)
        self.assertEqual(
            shift_to_business_day(datetime.date(2026, 12, 24)),
            datetime.date(2026, 12, 28),
        )

    def test_compute_upcoming_deadlines_with_project_config(self) -> None:
        cfg_path = Path(__file__).resolve().parents[1] / "config" / "tax_deadlines.json"
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        today = datetime.date(2026, 11, 15)
        results = compute_upcoming_deadlines(today, cfg, horizon_days=7)
        dates_by_title = {r["title"]: r for r in results}

        self.assertIn("Składki ZUS (spółki z o.o., akcyjne, stowarzyszenia, fundacje)", dates_by_title)
        zus_sp = dates_by_title["Składki ZUS (spółki z o.o., akcyjne, stowarzyszenia, fundacje)"]
        self.assertEqual(zus_sp["date"], "2026-11-16")
        self.assertTrue(zus_sp["shifted"])
        self.assertEqual(zus_sp["days_remaining"], 1)

        self.assertIn("Zaliczka na PIT / CIT oraz ryczałt od przychodów ewidencjonowanych", dates_by_title)
        pit = dates_by_title["Zaliczka na PIT / CIT oraz ryczałt od przychodów ewidencjonowanych"]
        self.assertEqual(pit["date"], "2026-11-20")
        self.assertFalse(pit["shifted"])
        self.assertEqual(pit["days_remaining"], 5)

    def test_generate_ics_calendar(self) -> None:
        ics = generate_ics_calendar([
            {
                "id": "pit-2026-11-20",
                "date": "2026-11-20",
                "title": "Zaliczka PIT",
                "description": "Zapłata zaliczki na mikrorachunek.",
            }
        ])
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("DTSTART;VALUE=DATE:20261120", ics)
        self.assertIn("SUMMARY:Zaliczka PIT", ics)
        self.assertIn("END:VCALENDAR", ics)


if __name__ == "__main__":
    unittest.main()
