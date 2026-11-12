"""
Główny punkt wejścia Porannego Briefingu (Main Entrypoint).
Łączy:
1. Moduł pogody (weather.py)
2. Moduł zbierania wiadomości podatkowych i ogólnych (news_tax.py)
3. Moduł syntezy AI (synthesizer.py)
4. Moduł wysyłki do Telegrama (telegram_sender.py)
"""

import os
from pathlib import Path
from weather import get_weather
from news_tax import get_latest_briefing_sources
from synthesizer import generate_ai_briefing
from telegram_sender import send_telegram_message


def load_env(env_path: Path):
    """Prosty czytnik pliku .env bez konieczności instalowania bibliotek zewnętrznych."""
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip()


def run_morning_briefing():
    base_dir = Path(__file__).resolve().parent
    load_env(base_dir / ".env")

    city = os.environ.get("CITY", "Warszawa")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    print(f"\n==========================================")
    print(f"🚀 URUCHAMIANIE PORANNEGO BRIEFINGU ({city})")
    print(f"==========================================")

    # 1. Pogoda
    print("\n[1/4] Pobieranie aktualnej prognozy pogody...")
    weather = get_weather(city)

    # 2. Wiadomości & Podatki
    print("[2/4] Skanowanie serwisów podatkowych, ZUS i gospodarczych...")
    sources = get_latest_briefing_sources()

    # 3. AI Synteza
    print("[3/4] Generowanie notatki analitycznej (Gemini)...")
    briefing_text = generate_ai_briefing(gemini_key, weather, sources)

    print("\n------------------- PODGLĄD NOTATKI -------------------")
    print(briefing_text)
    print("-------------------------------------------------------\n")

    # 4. Wysyłka na Telegram
    if bot_token and chat_id and bot_token != "twoj_token_bota_tutaj":
        print("[4/4] Wysyłanie notatki na Twój iPhone (Telegram)...")
        res = send_telegram_message(bot_token, chat_id, briefing_text)
        if res.get("success"):
            print("✅ SUKCES: Notatka została pomyślnie wysłana na Twój telefon!")
        else:
            print(f"❌ BŁĄD WYSYŁKI: {res.get('error')}")
    else:
        print("[4/4] Telegram: Brak tokenu/chat_id w pliku .env (pomijam wysyłkę na telefon).")
        print("💡 Aby otrzymywać notatki na telefonie, uzupełnij plik tools/morning_briefing/.env")


if __name__ == "__main__":
    run_morning_briefing()
