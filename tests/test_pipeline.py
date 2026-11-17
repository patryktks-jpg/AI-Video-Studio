"""Testy jednostkowe deduplikacji, strażnika strefy czasowej i dwuetapowego procesora AI."""

import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.ai_processor import KIS_MANDATORY_CAVEAT, GeminiClient, process_item_two_stage
from scripts.dedup import load_seen_ids, save_seen_ids, select_top_candidates
from scripts.main import check_schedule_guard, get_warsaw_now
from scripts.notifier import send_daily_notification


class TestDedup(unittest.TestCase):
    def test_load_and_save_seen_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            seen_file = Path(tmpdir) / "seen_ids.json"
            self.assertEqual(load_seen_ids(seen_file), set())

            save_seen_ids(seen_file, {"id-1"}, ["id-2", "id-1", "id-3"], max_history=100)
            loaded = load_seen_ids(seen_file)
            self.assertEqual(loaded, {"id-1", "id-2", "id-3"})

    def test_select_top_candidates_filters_seen_and_limits(self) -> None:
        candidates = [
            {"id": "old-1", "raw_title": "VAT", "full_text": "VAT ZUS", "published": "2026-11-15", "section_id": "interpretacje"},
            {"id": "new-low", "raw_title": "Notatka ogólna", "full_text": "Krótki wpis", "published": "2026-11-15", "section_id": "gospodarka"},
            {"id": "new-high", "raw_title": "Nowa stawka VAT i ryczałt", "full_text": "JDG KSeF podatek " * 80, "published": "2026-11-15", "section_id": "interpretacje"},
            {"id": "new-high", "raw_title": "Duplikat w tym samym rzucie", "full_text": "duplikat", "published": "2026-11-15", "section_id": "interpretacje"},
        ]
        selected = select_top_candidates(
            candidates,
            seen_ids={"old-1"},
            max_items=1,
            priority_keywords=["vat", "ryczałt", "ksef"],
            profile_tags=["JDG"],
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["id"], "new-high")


class TestScheduleAndTimezone(unittest.TestCase):
    def test_get_warsaw_now_winter_and_summer(self) -> None:
        winter_utc = datetime.datetime(2026, 1, 15, 6, 35, tzinfo=datetime.timezone.utc)
        winter_pl = get_warsaw_now(winter_utc)
        self.assertEqual(winter_pl.hour, 7)
        self.assertEqual(winter_pl.utcoffset(), datetime.timedelta(hours=1))

        summer_utc = datetime.datetime(2026, 7, 15, 5, 35, tzinfo=datetime.timezone.utc)
        summer_pl = get_warsaw_now(summer_utc)
        self.assertEqual(summer_pl.hour, 7)
        self.assertEqual(summer_pl.utcoffset(), datetime.timedelta(hours=2))

    def test_schedule_guard_window_and_force_time(self) -> None:
        deep_night = datetime.datetime(2026, 11, 15, 3, 45, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
        early_morning = datetime.datetime(2026, 11, 15, 5, 45, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
        morning = datetime.datetime(2026, 11, 15, 7, 45, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
        delayed_afternoon = datetime.datetime(2026, 11, 15, 14, 55, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
        late_night = datetime.datetime(2026, 11, 15, 23, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))

        with mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}):
            ok_night, reason_night = check_schedule_guard("2099-01-01", deep_night, force_time=False)
            self.assertFalse(ok_night)
            self.assertIn("04:30", reason_night)

            ok_early, _ = check_schedule_guard("2099-01-01", early_morning, force_time=False)
            self.assertTrue(ok_early)

            ok_morning, _ = check_schedule_guard("2099-01-01", morning, force_time=False)
            self.assertTrue(ok_morning)

            ok_delayed, _ = check_schedule_guard("2099-01-01", delayed_afternoon, force_time=False)
            self.assertTrue(ok_delayed)

            ok_late, reason_late = check_schedule_guard("2099-01-01", late_night, force_time=False)
            self.assertFalse(ok_late)
            self.assertIn("04:30–22:59", reason_late)

            ok_forced, _ = check_schedule_guard("2099-01-01", late_night, force_time=True)
            self.assertTrue(ok_forced)


class TestAiProcessorFallback(unittest.TestCase):
    def test_kis_mandatory_caveat_present_without_api_key(self) -> None:
        client = GeminiClient(api_key="", model_name="gemini-3.5-flash-lite")
        candidate = {
            "id": "kis-777",
            "raw_title": "Interpretacja w sprawie ryczałtu 8,5%",
            "full_text": "Sygnatura: 0112-KDIL2-2.4011.100.2026.1.AA\nData wydania: 2026-11-10\nTreść...",
            "published": "2026-11-14",
            "url": "https://eureka.mf.gov.pl/informacje/podglad/777",
            "source_name": "EUREKA MF (KIS)",
            "section_id": "interpretacje",
        }
        item, rejected = process_item_two_stage(
            client,
            candidate,
            company_profile={"profile_name": "Test JDG"},
            section_title="Interpretacje podatkowe",
        )
        self.assertFalse(rejected)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertIn(KIS_MANDATORY_CAVEAT, item["details"]["caveats"])


class TestNotifierDaily(unittest.TestCase):
    def test_notifier_skips_when_already_sent(self) -> None:
        today_str = get_warsaw_now().strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            sent_file = data_dir / "sent_log.json"
            sent_file.write_text(f'{{"{today_str}": "2026-11-17T08:00:00"}}', encoding="utf-8")
            with mock.patch("scripts.notifier.ROOT_DIR", Path(tmpdir)):
                res = send_daily_notification(force=False, allow_emergency_generate=False)
                self.assertEqual(res["status"], "already_sent")

    def test_notifier_alerts_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("scripts.notifier.ROOT_DIR", Path(tmpdir)), \
                 mock.patch("scripts.notifier.send_failure_alert") as mock_alert:
                res = send_daily_notification(force=True, allow_emergency_generate=False)
                self.assertEqual(res["status"], "error_missing_pill")
                mock_alert.assert_called_once()


if __name__ == "__main__":
    unittest.main()
