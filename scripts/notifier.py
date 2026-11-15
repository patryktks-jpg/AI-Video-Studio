"""
Moduł powiadomień (Zadanie 8 i 11).
Wysyła poranne powiadomienie (data, pogoda, 2-3 najważniejsze nagłówki, link do PWA)
oraz powiadomienie o awarii przez Telegram Bot API i opcjonalnie ntfy.sh.
"""

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Moduł powiadomień Porannej Pigułki")
    parser.add_argument("--failure", action="store_true", help="Wysyła powiadomienie o awarii pipeline'u")
    parser.add_argument("--reason", default="Błąd w zadaniu GitHub Actions.", help="Opis błędu")
    args = parser.parse_args()
    if args.failure:
        send_failure_alert(args.reason)
        print("Wysłano powiadomienie o awarii.")
