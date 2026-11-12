"""
Moduł redagowania notatki za pomocą modelu Gemini (AI Synthesizer).
Wykorzystuje oficjalne REST API Google Gemini (zero zewnętrznych bibliotek).
"""

import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional


def create_briefing_prompt(weather_info: Dict[str, Any], sources_data: Dict[str, Any]) -> str:
    """Tworzy instrukcję dla modelu AI z silnym naciskiem na interpretacje KIS/MF."""
    interpretations_text = "\n".join([
        f"- {it['title']}: {it.get('description', '')} [Link: {it['link']}]"
        for it in sources_data.get("interpretations", [])
    ])

    tax_items_text = "\n".join([
        f"- {it['title']} ({it['source']}): {it['description']} [Link: {it['link']}]"
        for it in sources_data.get("tax_and_zus", [])
    ])

    news_items_text = "\n".join([
        f"- {it['title']} ({it['source']}): {it['description']}"
        for it in sources_data.get("general_news", [])
    ])

    return f"""Jesteś profesjonalnym doradcą podatkowym i redaktorem codziennego briefingu biznesowego w Polsce.
Przygotuj dzisiejszy poranny przegląd w formie estetycznej, zwartej notatki na Telegram.

DANE WEJŚCIOWE:

[POGODA]:
{weather_info.get('summary')}

[NOWO WYDANE INTERPRETACJE PODATKOWE I PRAKTYKA KIS/MF]:
{interpretations_text}

[ZMIANY W PODATKACH I ZUS]:
{tax_items_text}

[NAJWAŻNIEJSZE WYDARZENIA - OGÓLNE]:
{news_items_text}

WYTYCZNE FORMATOWANIA (TELEGRAM MARKDOWN):
1. Nagłówek: 📋 *PORANNY BRIEFING BIZNESOWY* oraz sekcja pogody z miastem.
2. SEKCJA 1 (KLUCZOWA): 🏛️ *NOWE INTERPRETACJE KIS & ZMIANY PODATKOWE*:
   - Jeśli są podane interpretacje skarbowe lub orzeczenia, opisz 2-3 z nich: wyjaśnij zwięźle, o co w nich chodziło i co to w praktyce oznacza dla przedsiębiorcy/podatnika.
   - Wypunktuj najważniejsze zmiany w ZUS i podatkach na dziś.
3. SEKCJA 2: 🌍 *PIGUŁKA ZE ŚWIATA & GOSPODARKI*:
   - 2-3 najważniejsze wydarzenia w krótkich, żołnierskich punktach.
4. Krótka biznesowa myśl/porada na udany dzień.
5. Pisz przystępnie, konkretnie i zwięźle, używaj estetycznych punktorów.
"""


def generate_ai_briefing(api_key: Optional[str], weather_info: Dict[str, Any], sources_data: Dict[str, Any]) -> str:
    """
    Wysyła zebrane dane do Gemini API i generuje gotową notatkę analityczną.
    """
    if not api_key:
        return _fallback_briefing(weather_info, sources_data)

    prompt = create_briefing_prompt(weather_info, sources_data)
    models_to_try = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-latest"]

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048
        }
    }

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            print(f"[Synthesizer] Próba z {model_name} nie powiodła się: {err[:120]}")
            continue
        except Exception as e:
            print(f"[Synthesizer] Błąd połączenia z {model_name}: {e}")
            continue

    print("[Synthesizer] Używam trybu awaryjnego (fallback).")
    return _fallback_briefing(weather_info, sources_data)


def _fallback_briefing(weather_info: Dict[str, Any], sources_data: Dict[str, Any]) -> str:
    """Szablon awaryjny gdy AI jest niedostępne."""
    interp_bullets = "\n".join([
        f"• *{it['title']}*\n  _{it['link']}_"
        for it in sources_data.get("interpretations", [])[:3]
    ])
    tax_bullets = "\n".join([
        f"• *{it['title']}* ({it['source']})"
        for it in sources_data.get("tax_and_zus", [])[:3]
    ])
    news_bullets = "\n".join([
        f"• *{it['title']}* ({it['source']})"
        for it in sources_data.get("general_news", [])[:3]
    ])

    return (
        f"📋 *PORANNY BRIEFING BIZNESOWY*\n\n"
        f"{weather_info.get('summary', '')}\n\n"
        f"🏛️ *NOWE INTERPRETACJE PODATKOWE KIS:*\n"
        f"{interp_bullets}\n\n"
        f"⚖️ *PODATKI I ZUS:*\n"
        f"{tax_bullets}\n\n"
        f"🌍 *NAJWAŻNIEJSZE WYDARZENIA:*\n"
        f"{news_bullets}\n"
    )


if __name__ == "__main__":
    from weather import get_weather
    from news_tax import get_latest_briefing_sources
    import os

    print("--- Test modułu z interpretacjami ---")
    pogoda = get_weather("Brzesko")
    zrodla = get_latest_briefing_sources()
    key = os.environ.get("GEMINI_API_KEY")
    notatka = generate_ai_briefing(key, pogoda, zrodla)
    print(notatka)
