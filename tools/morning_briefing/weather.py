"""
Moduł pobierania pogody (Weather Module).
Wykorzystuje darmowe API Open-Meteo (bez konieczności posiadania klucza API).
Działa w oparciu o bibliotekę standardową Pythona (urllib).
"""

import json
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional


# Wstępna mapa współrzędnych dla popularnych polskich miast (szybki fallback)
POLISH_CITIES = {
    "warszawa": {"lat": 52.2297, "lon": 21.0122},
    "brzesko": {"lat": 49.9691, "lon": 20.6061},
    "krakow": {"lat": 50.0647, "lon": 19.9450},
    "kraków": {"lat": 50.0647, "lon": 19.9450},
    "wroclaw": {"lat": 51.1079, "lon": 17.0385},
    "wrocław": {"lat": 51.1079, "lon": 17.0385},
    "gdansk": {"lat": 54.3520, "lon": 18.6466},
    "gdańsk": {"lat": 54.3520, "lon": 18.6466},
    "poznan": {"lat": 52.4064, "lon": 16.9252},
    "poznań": {"lat": 52.4064, "lon": 16.9252},
    "katowice": {"lat": 50.2649, "lon": 19.0238},
    "lodz": {"lat": 51.7592, "lon": 19.4560},
    "łódź": {"lat": 51.7592, "lon": 19.4560},
    "szczecin": {"lat": 53.4285, "lon": 14.5528},
    "lublin": {"lat": 51.2465, "lon": 22.5684},
    "rzeszow": {"lat": 50.0412, "lon": 21.9991},
    "rzeszów": {"lat": 50.0412, "lon": 21.9991},
    "bialystok": {"lat": 53.1325, "lon": 23.1688},
    "białystok": {"lat": 53.1325, "lon": 23.1688},
}

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
    80: "Przelotne opady deszczu 🌦️",
    81: "Ulewne przelotne opady 🌧️",
    82: "Gwałtowne ulewy ⛈️",
    95: "Burza z piorunami ⚡",
    96: "Burza z gradem ⛈️",
}


def get_city_coordinates(city_name: str) -> Optional[Dict[str, float]]:
    """Zwraca współrzędne (lat, lon) dla podanego miasta."""
    city_lower = city_name.strip().lower()
    if city_lower in POLISH_CITIES:
        return POLISH_CITIES[city_lower]

    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city_name)}&count=1&language=pl&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "MorningBriefingApp/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("results"):
                res = data["results"][0]
                return {"lat": res["latitude"], "lon": res["longitude"]}
    except Exception as e:
        print(f"[Ostrzeżenie] Nie udało się ustalić współrzędnych dla {city_name}: {e}")

    # Domyślny fallback: Warszawa
    return POLISH_CITIES["warszawa"]


def get_weather(city_name: str = "Warszawa") -> Dict[str, Any]:
    """
    Pobiera aktualną pogodę oraz prognozę na dzisiejszy dzień.
    """
    coords = get_city_coordinates(city_name) or POLISH_CITIES["warszawa"]
    lat, lon = coords["lat"], coords["lon"]

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
        f"&timezone=auto"
    )

    req = urllib.request.Request(url, headers={"User-Agent": "MorningBriefingApp/1.0"})
    with urllib.request.urlopen(req, timeout=8) as response:
        data = json.loads(response.read().decode("utf-8"))

    current = data.get("current", {})
    daily = data.get("daily", {})

    weather_code = current.get("weather_code", 0)
    weather_desc = WMO_WEATHER_CODES.get(weather_code, "Zmienna aura")

    temp_now = current.get("temperature_2m", "--")
    wind_now = current.get("wind_speed_10m", "--")
    temp_max = daily.get("temperature_2m_max", ["--"])[0]
    temp_min = daily.get("temperature_2m_min", ["--"])[0]
    rain_prob = daily.get("precipitation_probability_max", [0])[0]

    return {
        "city": city_name.capitalize(),
        "temp_now": temp_now,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "condition": weather_desc,
        "wind_speed_kmh": wind_now,
        "rain_probability_pct": rain_prob,
        "summary": (
            f"📍 Pogoda: {city_name.capitalize()} | {weather_desc}\n"
            f"🌡️ Aktualnie: {temp_now}°C (min: {temp_min}°C, max: {temp_max}°C)\n"
            f"🌧️ Szansa opadów: {rain_prob}% | Wiatr: {wind_now} km/h"
        ),
    }


if __name__ == "__main__":
    print("--- Test modułu pogody ---")
    pogoda = get_weather("Warszawa")
    print(pogoda["summary"])
