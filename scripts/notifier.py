"""
Moduł powiadomień (Zadanie 8 i 11).
Wysyła poranne powiadomienie (data, pogoda, 2-3 najważniejsze nagłówki, link do PWA)
oraz powiadomienie o awarii przez Telegram Bot API i opcjonalnie ntfy.sh.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _last_sunday(year: int, month: int) -> datetime.date:
    """Wyznacza ostatnią niedzielę danego miesiąca (zmiana czasu CET/CEST w Polsce)."""
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    last_day = next_month - datetime.timedelta(days=1)
    offset = (last_day.weekday() + 1) % 7
    return last_day - datetime.timedelta(days=offset)


def get_warsaw_now(utc_now: Optional[datetime.datetime] = None) -> datetime.datetime:
    """Zwraca dokładny czas lokalny w strefie Europe/Warsaw (z obsługą zmiany czasu)."""
    now_utc = utc_now or datetime.datetime.now(datetime.timezone.utc)
    dst_start = datetime.datetime.combine(_last_sunday(now_utc.year, 3), datetime.time(1, 0), tzinfo=datetime.timezone.utc)
    dst_end = datetime.datetime.combine(_last_sunday(now_utc.year, 10), datetime.time(1, 0), tzinfo=datetime.timezone.utc)
    offset_hours = 2 if dst_start <= now_utc < dst_end else 1
    warsaw_tz = datetime.timezone(datetime.timedelta(hours=offset_hours))
    return now_utc.astimezone(warsaw_tz)


def load_dotenv_if_present() -> None:
    """Wczytuje plik .env z katalogu głównego repozytorium dla uruchomień lokalnych."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def format_notification_message(pill: Dict[str, Any], app_url: str) -> str:
    """Buduje zwięzłe powiadomienie z najważniejszymi nagłówkami i linkiem do PWA."""
    date_str = pill.get("date", "")
    weather = pill.get("weather", {})
    city = weather.get("city", "Brzesko")
    if weather.get("status") == "ok":
        weather_line = (
            f"🌤️ {city}: {weather.get('temp_now', '--')}°C "
            f"(odcz. {weather.get('apparent_temp', '--')}°C), {weather.get('practical_tip', '')}"
        )
    else:
        weather_line = f"🌤️ {city}: brak prognozy"

    top_headlines: List[str] = []
    for sec in pill.get("sections", []):
        for it in sec.get("items", []):
            if it.get("importance") == "high":
                top_headlines.append(f"• {it['headline']}")
                if len(top_headlines) >= 3:
                    break
        if len(top_headlines) >= 3:
            break

    if not top_headlines:
        for sec in pill.get("sections", []):
            for it in sec.get("items", []):
                top_headlines.append(f"• {it['headline']}")
                if len(top_headlines) >= 3:
                    break
            if len(top_headlines) >= 3:
                break

    headlines_block = "\n".join(top_headlines) if top_headlines else "• Brak nowych pozycji na dziś."
    deadlines_count = len(pill.get("deadlines", []))
    dl_line = f"\n📅 Nadchodzące terminy (7 dni): {deadlines_count}" if deadlines_count else ""

    return (
        f"☕ Poranna pigułka ({date_str})\n\n"
        f"{weather_line}{dl_line}\n\n"
        f"Najważniejsze dziś:\n{headlines_block}\n\n"
        f"👉 Otwórz aplikację:\n{app_url}"
    )


def send_telegram(bot_token: str, chat_id: str, text: str) -> Dict[str, Any]:
    """Wysyła czysty komunikat tekstowy przez Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return {"ok": True, "response": json.loads(resp.read().decode("utf-8"))}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def send_ntfy(topic: str, title: str, text: str, click_url: str = "") -> Dict[str, Any]:
    """Wysyła opcjonalne powiadomienie przez darmowy serwer ntfy.sh."""
    url = f"https://ntfy.sh/{topic.strip()}"
    headers = {"Title": title.encode("ascii", "ignore").decode("ascii")}
    if click_url:
        headers["Click"] = click_url
    req = urllib.request.Request(url, data=text.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "status": resp.status}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def dispatch_notifications(pill: Dict[str, Any], app_url: str, ntfy_topic: str = "") -> Dict[str, Any]:
    """Wysyła powiadomienia wszystkimi skonfigurowanymi kanałami."""
    load_dotenv_if_present()
    msg = format_notification_message(pill, app_url=app_url)
    results: Dict[str, Any] = {}

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if bot_token and chat_id:
        results["telegram"] = send_telegram(bot_token, chat_id, msg)

    env_topic = os.environ.get("NTFY_TOPIC", ntfy_topic).strip()
    if env_topic:
        results["ntfy"] = send_ntfy(env_topic, f"Poranna Pigulka {pill.get('date', '')}", msg, click_url=app_url)

    return results


def send_failure_alert(reason: str = "Nieznany błąd podczas generowania porannej pigułki.") -> None:
    """Wysyła alert awaryjny na Telegram/ntfy w razie błędu pipeline'u."""
    load_dotenv_if_present()
    run_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    link = f"\nLogi uruchomienia: {run_url}/{repo}/actions/runs/{run_id}" if repo and run_id else ""

    text = (
        f"⚠️ AWARIA: Dzisiejsza Poranna Pigułka nie została wygenerowana!\n\n"
        f"Przyczyna: {reason}{link}"
    )

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if bot_token and chat_id:
        send_telegram(bot_token, chat_id, text)

    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if topic:
        send_ntfy(topic, "AWARIA Porannej Pigulki", text)


def send_daily_notification(force: bool = False, allow_emergency_generate: bool = True) -> Dict[str, Any]:
    """
    Sprawdza stan dzisiejszej pigułki i wysyła powiadomienie dokładnie o 08:00 (Krok 3).
    Jeśli pigułka nie została przygotowana wcześniej w nocy, próbuje szybkiej generacji awaryjnej.
    Jeśli nawet to zawiedzie, wysyła alert awaryjny o 08:00.
    """
    load_dotenv_if_present()
    now_pl = get_warsaw_now()
    today_str = now_pl.strftime("%Y-%m-%d")
    data_dir = ROOT_DIR / "data"
    pill_file = data_dir / f"{today_str}.json"
    sent_log_file = data_dir / "sent_log.json"

    # 1. Sprawdzenie czy pigułka na dziś została już wysłana
    if not force and sent_log_file.exists():
        try:
            with open(sent_log_file, "r", encoding="utf-8") as f:
                sent_log = json.load(f)
            if sent_log.get(today_str):
                print(f"[Notifier] Powiadomienie na {today_str} zostało już wysłane o {sent_log[today_str]}. Pomijam duplikat.")
                return {"status": "already_sent", "date": today_str}
        except Exception:
            pass

    # 2. Jeśli plik nie istnieje, próba awaryjnej generacji na żywo
    if not pill_file.exists() and allow_emergency_generate:
        print(f"[Notifier] Brak pliku {today_str}.json o {now_pl.strftime('%H:%M:%S')} — uruchamiam awaryjną generację...")
        try:
            from scripts.main import build_daily_pill, sync_data_to_app, update_archive_index
            from scripts.validator import validate_pill_document
            from scripts.dedup import load_seen_ids, save_seen_ids

            sources_cfg_path = ROOT_DIR / "config" / "sources.json"
            profile_path = ROOT_DIR / "config" / "company_profile.json"
            with open(sources_cfg_path, "r", encoding="utf-8") as f:
                sources_cfg = json.load(f)
            with open(profile_path, "r", encoding="utf-8") as f:
                company_profile = json.load(f)

            pill_doc, new_ids = build_daily_pill(
                sources_cfg=sources_cfg,
                company_profile=company_profile,
                warsaw_now=now_pl,
                dry_run=False,
                max_per_section_override=2,
            )
            is_valid, _ = validate_pill_document(pill_doc)
            if is_valid:
                data_dir.mkdir(parents=True, exist_ok=True)
                with open(pill_file, "w", encoding="utf-8") as f:
                    json.dump(pill_doc, f, ensure_ascii=False, indent=2)
                seen_path = data_dir / "seen_ids.json"
                seen_ids = load_seen_ids(seen_path)
                save_seen_ids(seen_path, seen_ids, new_ids)
                update_archive_index(data_dir)
                sync_data_to_app(data_dir, ROOT_DIR / "app" / "data")
                print(f"[Notifier] Awaryjna generacja pigułki na {today_str} powiodła się.")
        except Exception as exc:
            print(f"[Notifier] Awaryjna generacja nie powiodła się: {exc}")

    # 3. Jeśli nadal brak pliku — wyślij natychmiast alert awaryjny o 08:00
    if not pill_file.exists():
        reason = f"Brak wygenerowanej pigułki na dzień {today_str} o godzinie {now_pl.strftime('%H:%M:%S')} (Europe/Warsaw)."
        print(f"[Notifier] {reason}")
        send_failure_alert(reason)
        return {"status": "error_missing_pill", "reason": reason}

    # 4. Wczytaj wygenerowaną pigułkę i wyślij powiadomienie
    with open(pill_file, "r", encoding="utf-8") as f:
        pill = json.load(f)

    sources_cfg_path = ROOT_DIR / "config" / "sources.json"
    app_url = "https://patryktks-jpg.github.io/AI-Video-Studio/"
    ntfy_topic = ""
    if sources_cfg_path.exists():
        try:
            with open(sources_cfg_path, "r", encoding="utf-8") as f:
                sc = json.load(f)
            app_url = sc.get("notifications", {}).get("app_url", app_url)
            ntfy_topic = sc.get("notifications", {}).get("ntfy_topic", "")
        except Exception:
            pass

    res = dispatch_notifications(pill, app_url=app_url, ntfy_topic=ntfy_topic)

    # 5. Zapisz datę wysłania w sent_log.json
    try:
        sent_log = {}
        if sent_log_file.exists():
            with open(sent_log_file, "r", encoding="utf-8") as f:
                sent_log = json.load(f)
        sent_log[today_str] = now_pl.isoformat(timespec="seconds")
        if len(sent_log) > 30:
            keys = sorted(sent_log.keys())[-30:]
            sent_log = {k: sent_log[k] for k in keys}
        with open(sent_log_file, "w", encoding="utf-8") as f:
            json.dump(sent_log, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[Notifier] Ostrzeżenie przy zapisie sent_log.json: {exc}")

    return {"status": "ok", "results": res}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Moduł powiadomień Porannej Pigułki")
    parser.add_argument("--send-daily", action="store_true", help="Wysyła poranne powiadomienie na dziś (z alertem awaryjnym w razie braku)")
    parser.add_argument("--force", action="store_true", help="Wymusza wysyłkę nawet jeśli dziś już wysłano")
    parser.add_argument("--failure", action="store_true", help="Wysyła powiadomienie o awarii pipeline'u")
    parser.add_argument("--reason", default="Błąd w zadaniu GitHub Actions.", help="Opis błędu")
    args = parser.parse_args()

    if args.failure:
        send_failure_alert(args.reason)
        print("Wysłano powiadomienie o awarii.")
    elif args.send_daily:
        out = send_daily_notification(force=args.force)
        print(f"Wynik wysyłki: {json.dumps(out, ensure_ascii=False)}")
