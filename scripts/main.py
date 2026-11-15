"""
Główny orkiestrator generowania codziennej „Porannej Pigułki” (Zadanie 1, 4, 5, 11).
Obsługuje tryb --dry-run (bez zapisu i powiadomień), strażnika strefy czasowej Europe/Warsaw,
niezawodność źródeł, dwuetapowe AI, walidację schematem JSON oraz logi uruchomienia.
"""

import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ai_processor import GeminiClient, process_item_two_stage
from scripts.deadlines_calc import load_and_compute_deadlines
from scripts.dedup import load_seen_ids, save_seen_ids, select_top_candidates
from scripts.notifier import dispatch_notifications, load_dotenv_if_present
from scripts.sources.economy_world import fetch_economy_world
from scripts.sources.eureka_kis import fetch_eureka_interpretations
from scripts.sources.legislation import fetch_legislation
from scripts.sources.markets import fetch_markets
from scripts.sources.weather import fetch_weather
from scripts.sources.zus_gov import fetch_zus_gov
from scripts.validator import validate_pill_document


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
APP_DATA_DIR = ROOT_DIR / "app" / "data"


def _last_sunday(year: int, month: int) -> datetime.date:
    """Wyznacza ostatnią niedzielę danego miesiąca (zmiana czasu CET/CEST w Polsce)."""
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    last_day = next_month - datetime.timedelta(days=1)
    offset = (last_day.weekday() + 1) % 7  # niedziela ma weekday() == 6 -> offset 0
    return last_day - datetime.timedelta(days=offset)


def get_warsaw_now(utc_now: Optional[datetime.datetime] = None) -> datetime.datetime:
    """Zwraca dokładny czas lokalny w strefie Europe/Warsaw (z obsługą zmiany czasu)."""
    now_utc = utc_now or datetime.datetime.now(datetime.timezone.utc)
    dst_start = datetime.datetime.combine(_last_sunday(now_utc.year, 3), datetime.time(1, 0), tzinfo=datetime.timezone.utc)
    dst_end = datetime.datetime.combine(_last_sunday(now_utc.year, 10), datetime.time(1, 0), tzinfo=datetime.timezone.utc)
    offset_hours = 2 if dst_start <= now_utc < dst_end else 1
    warsaw_tz = datetime.timezone(datetime.timedelta(hours=offset_hours))
    return now_utc.astimezone(warsaw_tz)


def check_schedule_guard(today_str: str, warsaw_now: datetime.datetime, force_time: bool) -> Tuple[bool, str]:
    """
    Strażnik dla podwójnego harmonogramu cron w GitHub Actions (czas letni / zimowy).
    Zapobiega podwójnemu uruchomieniu tego samego dnia oraz wysyłce spóźnionej po awarii kolejki.
    """
    if force_time:
        return True, "Tryb --force-time: pominięto ograniczenie okna."

    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if event_name != "schedule":
        return True, "Uruchomienie ręczne lub testowe."

    today_file = DATA_DIR / f"{today_str}.json"
    if today_file.exists():
        return False, f"Pigułka na {today_str} już istnieje (prawdopodobnie wygenerowana przez drugi cron UTC)."

    if warsaw_now.hour < 6 or (warsaw_now.hour == 6 and warsaw_now.minute < 30) or warsaw_now.hour >= 9:
        return False, (
            f"Poza porannym oknem (Europe/Warsaw: {warsaw_now.strftime('%H:%M')}). "
            "Oczekiwane okno to 06:30–08:59."
        )
    return True, "Okno poranne potwierdzone."


def load_json_file(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_archive_index(data_dir: Path) -> List[Dict[str, Any]]:
    """Buduje plik data/index.json z listą dostępnych dni dla PWA."""
    entries: List[Dict[str, Any]] = []
    for p in sorted(data_dir.glob("20??-??-??.json"), reverse=True):
        try:
            doc = load_json_file(p)
            items_count = sum(len(sec.get("items", [])) for sec in doc.get("sections", []))
            entries.append({
                "date": doc.get("date", p.stem),
                "generated_at": doc.get("generated_at", ""),
                "items_count": items_count,
                "weather_summary": doc.get("weather", {}).get("condition", ""),
            })
        except Exception:
            continue

    index_payload = {
        "updated_at": get_warsaw_now().isoformat(timespec="seconds"),
        "days": entries,
    }
    with open(data_dir / "index.json", "w", encoding="utf-8") as f:
        json.dump(index_payload, f, ensure_ascii=False, indent=2)
    return entries


def sync_data_to_app(data_dir: Path, app_data_dir: Path) -> None:
    """Kopiuje pliki wyjściowe JSON z /data do /app/data na potrzeby GitHub Pages i Service Workera."""
    app_data_dir.mkdir(parents=True, exist_ok=True)
    for src_file in data_dir.glob("*.json"):
        if src_file.name == "seen_ids.json":
            continue
        shutil.copy2(src_file, app_data_dir / src_file.name)


def build_daily_pill(
    sources_cfg: Dict[str, Any],
    company_profile: Dict[str, Any],
    warsaw_now: datetime.datetime,
    dry_run: bool = False,
    max_per_section_override: Optional[int] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Wykonuje pełny pipeline zbierania, deduplikacji, dwuetapowego AI oraz walidacji."""
    today_str = warsaw_now.strftime("%Y-%m-%d")
    seen_path = DATA_DIR / "seen_ids.json"
    seen_ids = load_seen_ids(seen_path)

    max_per_section = max_per_section_override or int(sources_cfg.get("max_items_per_section", 5))
    max_source_chars = int(sources_cfg.get("max_source_chars_per_item", 6000))
    priority_kws = sources_cfg.get("selection_criteria", {}).get("priority_keywords", [])
    profile_tags = company_profile.get("priority_tags", [])

    sources_status: Dict[str, str] = {}

    # 1. Pogoda i rynki (liczby bezpośrednio z API, bez udziału AI)
    weather_data = (
        fetch_weather(sources_cfg.get("weather", {}))
        if sources_cfg.get("weather", {}).get("enabled", True)
        else {"city": "Brzesko", "status": "unavailable"}
    )
    sources_status["weather"] = weather_data.get("status", "unavailable")

    markets_data = (
        fetch_markets(sources_cfg.get("markets", {}))
        if sources_cfg.get("markets", {}).get("enabled", True)
        else {"status": "unavailable"}
    )
    sources_status["markets"] = markets_data.get("status", "unavailable")

    # 2. Terminy podatkowe (wyliczane programowo)
    deadlines = load_and_compute_deadlines(today=warsaw_now.date(), horizon_days=7)

    # 3. Pobieranie źródeł tekstowych
    eureka_res = (
        fetch_eureka_interpretations(
            sources_cfg.get("eureka_kis", {}),
            seen_ids=seen_ids,
            max_source_chars=max_source_chars,
        )
        if sources_cfg.get("eureka_kis", {}).get("enabled", True)
        else {"status": "unavailable", "items": []}
    )
    sources_status["eureka_kis"] = eureka_res.get("status", "unavailable")

    legislation_res = (
        fetch_legislation(sources_cfg.get("legislation", {}), seen_ids=seen_ids)
        if sources_cfg.get("legislation", {}).get("enabled", True)
        else {"status": "unavailable", "items": []}
    )
    sources_status["legislation"] = legislation_res.get("status", "unavailable")

    zus_gov_res = (
        fetch_zus_gov(sources_cfg.get("zus_gov", {}), seen_ids=seen_ids)
        if sources_cfg.get("zus_gov", {}).get("enabled", True)
        else {"status": "unavailable", "items": []}
    )
    sources_status["zus_gov"] = zus_gov_res.get("status", "unavailable")

    economy_res = (
        fetch_economy_world(sources_cfg.get("economy_world", {}), seen_ids=seen_ids)
        if sources_cfg.get("economy_world", {}).get("enabled", True)
        else {"status": "unavailable", "items": []}
    )
    sources_status["economy_world"] = economy_res.get("status", "unavailable")

    # 4. Wybór i deduplikacja kandydatów na sekcję
    section_configs = [
        {
            "id": "interpretacje",
            "title": "Interpretacje podatkowe (KIS)",
            "candidates": eureka_res.get("items", []),
            "source_ok": eureka_res.get("status") in ("ok", "partial"),
            "err": eureka_res.get("error", ""),
        },
        {
            "id": "podatki_zus",
            "title": "Zmiany w podatkach, ZUS i legislacji",
            "candidates": zus_gov_res.get("items", []) + legislation_res.get("items", []),
            "source_ok": (
                zus_gov_res.get("status") in ("ok", "partial")
                or legislation_res.get("status") in ("ok", "partial")
            ),
            "err": "; ".join(x for x in (zus_gov_res.get("error", ""), legislation_res.get("error", "")) if x),
        },
        {
            "id": "gospodarka_swiat",
            "title": "Wydarzenia ze świata i gospodarki",
            "candidates": economy_res.get("items", []),
            "source_ok": economy_res.get("status") in ("ok", "partial"),
            "err": economy_res.get("error", ""),
        },
    ]

    # 5. Klient Gemini AI (dwuetapowy)
    gemini_client = GeminiClient(
        api_key=os.environ.get("GEMINI_API_KEY", ""),
        model_name=sources_cfg.get("ai_model", "gemini-3.5-flash-lite"),
        fallback_models=sources_cfg.get("ai_fallback_models", []),
        delay_seconds=float(sources_cfg.get("ai_delay_seconds", 2.0)),
        max_retries=int(sources_cfg.get("ai_max_retries", 3)),
    )

    sections_output: List[Dict[str, Any]] = []
    published_new_ids: List[str] = []
    rejected_count = 0
    low_confidence_count = 0

    for sec_cfg in section_configs:
        selected = select_top_candidates(
            sec_cfg["candidates"],
            seen_ids=seen_ids,
            max_items=max_per_section,
            priority_keywords=priority_kws,
            profile_tags=profile_tags,
        )

        processed_items: List[Dict[str, Any]] = []
        for cand in selected:
            item_obj, was_rejected = process_item_two_stage(
                client=gemini_client,
                candidate=cand,
                company_profile=company_profile,
                section_title=sec_cfg["title"],
            )
            if was_rejected:
                rejected_count += 1
            if item_obj:
                if item_obj.get("confidence") == "low":
                    low_confidence_count += 1
                processed_items.append(item_obj)
                published_new_ids.append(item_obj["id"])

        if not sec_cfg["source_ok"] and not processed_items:
            sec_status = "unavailable"
            status_msg = f"Źródło chwilowo niedostępne ({sec_cfg['err']})."
        elif not processed_items:
            sec_status = "empty"
            status_msg = "Brak nowych publikacji od ostatniego uruchomienia."
        else:
            sec_status = "ok"
            status_msg = ""

        sections_output.append({
            "id": sec_cfg["id"],
            "title": sec_cfg["title"],
            "status": sec_status,
            "status_message": status_msg,
            "items": processed_items,
        })

    pill_doc: Dict[str, Any] = {
        "date": today_str,
        "generated_at": warsaw_now.isoformat(timespec="seconds"),
        "weather": weather_data,
        "markets": markets_data,
        "deadlines": deadlines,
        "sections": sections_output,
        "meta": {
            "ai_model": sources_cfg.get("ai_model", "gemini-3.5-flash-lite") if gemini_client.is_configured() else "deterministic-fallback",
            "ai_calls": gemini_client.calls_count,
            "estimated_tokens": gemini_client.estimated_tokens,
            "rejected_count": rejected_count,
            "low_confidence_count": low_confidence_count,
            "sources_status": sources_status,
            "run_mode": "dry-run" if dry_run else "production",
        },
    }
    return pill_doc, published_new_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Generator Porannej Pigułki Przedsiębiorcy")
    parser.add_argument("--dry-run", action="store_true", help="Test bez zapisu do /data i bez wysyłania powiadomień")
    parser.add_argument("--no-notify", action="store_true", help="Zapisuje JSON, ale pomija wysyłkę powiadomień")
    parser.add_argument("--force-time", action="store_true", help="Pomija strażnika okna czasowego harmonogramu")
    parser.add_argument("--max-per-section", type=int, default=None, help="Nadpisuje limit pozycji na sekcję")
    args = parser.parse_args()

    load_dotenv_if_present()
    warsaw_now = get_warsaw_now()
    today_str = warsaw_now.strftime("%Y-%m-%d")

    allowed, reason = check_schedule_guard(today_str, warsaw_now, force_time=args.force_time)
    if not allowed:
        print(f"[Harmonogram] Pominięto wykonanie: {reason}")
        return 0

    sources_cfg = load_json_file(CONFIG_DIR / "sources.json")
    company_profile = load_json_file(CONFIG_DIR / "company_profile.json")

    print(f"=== PORANNA PIGUŁKA ({today_str}, {warsaw_now.strftime('%H:%M:%S %Z')}) ===")
    print(f"Tryb: {'DRY-RUN' if args.dry_run else 'PRODUKCYJNY'}")

    pill_doc, new_ids = build_daily_pill(
        sources_cfg=sources_cfg,
        company_profile=company_profile,
        warsaw_now=warsaw_now,
        dry_run=args.dry_run,
        max_per_section_override=args.max_per_section,
    )

    is_valid, val_errors = validate_pill_document(pill_doc)
    if not is_valid:
        print("BŁĄD WALIDACJI SCHEMATU JSON:", file=sys.stderr)
        for err in val_errors:
            print(f" - {err}", file=sys.stderr)
        return 1

    meta = pill_doc["meta"]
    print(
        f"Status źródeł: {json.dumps(meta['sources_status'], ensure_ascii=False)}\n"
        f"Wywołania AI: {meta['ai_calls']} | Tokeny: {meta['estimated_tokens']} | "
        f"Niska pewność: {meta['low_confidence_count']} | Odrzucone: {meta['rejected_count']}"
    )

    if args.dry_run:
        total_items = sum(len(s["items"]) for s in pill_doc["sections"])
        print(f"[DRY-RUN] Walidacja OK. Wygenerowano {total_items} pozycji. Nic nie zapisano ani nie wysłano.")
        return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_file = DATA_DIR / f"{today_str}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(pill_doc, f, ensure_ascii=False, indent=2)

    seen_path = DATA_DIR / "seen_ids.json"
    seen_ids = load_seen_ids(seen_path)
    save_seen_ids(seen_path, seen_ids, new_ids)
    update_archive_index(DATA_DIR)
    sync_data_to_app(DATA_DIR, APP_DATA_DIR)
    print(f"Zapisano pigułkę do {out_file} oraz zsynchronizowano z {APP_DATA_DIR}.")

    if not args.no_notify:
        notif_cfg = sources_cfg.get("notifications", {})
        notify_res = dispatch_notifications(
            pill_doc,
            app_url=notif_cfg.get("app_url", ""),
            ntfy_topic=notif_cfg.get("ntfy_topic", ""),
        )
        print(f"Wynik powiadomień: {json.dumps(notify_res, ensure_ascii=False)}")
    else:
        print("Tryb --no-notify: pominięto wysyłkę powiadomień.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
