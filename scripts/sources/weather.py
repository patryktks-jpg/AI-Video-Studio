"""
Moduł pogody (Open-Meteo) dla Brzeska (32-800).
Pobiera temperaturę aktualną i odczuwalną, wiatr oraz prognozę godzinową opadów,
generując praktyczną wskazówkę na dany dzień (np. o której zabrać parasol).
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sources.http_utils import fetch_json

WMO_WEATHER_CODES = {
    0: "Bezchmurnie ☀️",
    1: "Głównie słonecznie 🌤️",
    2: "Częściowe zachmurzenie ⛅",
    3: "Pochmurno ☁️",
    45: "Mgła 🌫️",
    48: "Oszroniona mgła 🌫️",
    51: "Lekka mżawka 🌦️",
    53: "Umiarkowana mżawka 🌧️",
    55: "Gęsta mżawka 🌧️",
    61: "Lekki deszcz 🌦️",
    63: "Umiarkowany deszcz 🌧️",
    65: "Ulewny deszcz 🌧️",
    71: "Lekki śnieg 🌨️",
    73: "Umiarkowany śnieg 🌨️",
    75: "Mocny śnieg ❄️",
    80: "Przelotne opady 🌦️",
    81: "Ulewne przelotne opady 🌧️",
    82: "Gwałtowne ulewy ⛈️",
    95: "Burza ⚡",
    96: "Burza z gradem ⛈️",
}


def build_practical_tip(
    hourly_forecast: List[Dict[str, Any]],
    apparent_temp: float,
    wind_speed: float,
) -> str:
    """Buduje jednozdaniową, praktyczną wskazówkę na podstawie godzinowych prognoz."""
    rainy_hours = [h for h in hourly_forecast if h["rain_prob"] >= 50]
    if rainy_hours:
        first_rain = rainy_hours[0]["hour"]
        max_prob = max(h["rain_prob"] for h in rainy_hours)
        if first_rain <= "09:00":
            rain_part = f"Parasol wskazany od rana (szansa opadów do {int(max_prob)}%)."
        else:
            rain_part = f"Parasol wskazany od około {first_rain} (opady do {int(max_prob)}%)."
    else:
        rain_part = "Dzień bez większego ryzyka opadów."

    if apparent_temp is not None and apparent_temp <= 3:
        clothing_part = "Odczuwalnie chłodno — ciepła kurtka niezbędna."
    elif wind_speed is not None and wind_speed >= 30:
        clothing_part = "Uwaga na silniejszy wiatr."
    else:
        clothing_part = ""

    return f"{rain_part} {clothing_part}".strip()


def parse_weather_payload(data: Dict[str, Any], city: str, postal_code: str = "") -> Dict[str, Any]:
    """Przetwarza surową odpowiedź JSON z Open-Meteo na ustrukturyzowany obiekt pigułki."""
    current = data.get("current", {})
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})

    weather_code = int(current.get("weather_code", 0) or 0)
    condition = WMO_WEATHER_CODES.get(weather_code, "Zmienna aura")

    temp_now = current.get("temperature_2m")
    apparent_temp = current.get("apparent_temperature", temp_now)
    wind_speed = current.get("wind_speed_10m")

    temp_max_list = daily.get("temperature_2m_max") or [None]
    temp_min_list = daily.get("temperature_2m_min") or [None]
    rain_max_list = daily.get("precipitation_probability_max") or [0]

    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    probs = hourly.get("precipitation_probability") or []

    hourly_forecast: List[Dict[str, Any]] = []
    # Pierwszy dzień prognozy (24 godziny), wybieramy okno dzienne 07:00 - 21:00
    for idx, ts in enumerate(times[:24]):
        hour_str = ts.split("T")[1][:5] if "T" in ts else ts
        if "07:00" <= hour_str <= "21:00":
            t_val = temps[idx] if idx < len(temps) else 0.0
            p_val = probs[idx] if idx < len(probs) else 0
            hourly_forecast.append({
                "hour": hour_str,
                "temp": float(t_val),
                "rain_prob": int(p_val or 0),
            })

    tip = build_practical_tip(hourly_forecast, apparent_temp, wind_speed)

    return {
        "city": city,
        "postal_code": postal_code,
        "status": "ok",
        "temp_now": temp_now,
        "apparent_temp": apparent_temp,
        "temp_min": temp_min_list[0],
        "temp_max": temp_max_list[0],
        "wind_speed_kmh": wind_speed,
        "rain_probability_max": rain_max_list[0],
        "condition": condition,
        "practical_tip": tip,
        "hourly_forecast": hourly_forecast,
    }


def fetch_weather(config: Dict[str, Any]) -> Dict[str, Any]:
    """Pobiera prognozę pogody Open-Meteo według konfiguracji."""
    city = config.get("city", "Brzesko")
    postal_code = config.get("postal_code", "32-800")
    lat = config.get("lat", 49.9691)
    lon = config.get("lon", 20.6061)

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
        f"&hourly=temperature_2m,precipitation_probability"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&forecast_days=1&timezone=Europe%2FWarsaw"
    )
    try:
        data = fetch_json(url, timeout=10)
        return parse_weather_payload(data, city=city, postal_code=postal_code)
    except Exception as exc:
        return {
            "city": city,
            "postal_code": postal_code,
            "status": "unavailable",
            "condition": "Źródło chwilowo niedostępne",
            "practical_tip": "Nie udało się pobrać prognozy pogody.",
            "hourly_forecast": [],
            "error": str(exc),
        }


if __name__ == "__main__":
    sample_cfg = {"city": "Brzesko", "postal_code": "32-800", "lat": 49.9691, "lon": 20.6061}
    print(json.dumps(fetch_weather(sample_cfg), ensure_ascii=False, indent=2))
